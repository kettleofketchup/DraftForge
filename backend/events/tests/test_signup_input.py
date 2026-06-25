from datetime import timedelta
from unittest.mock import patch as mock_patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType, Organization
from events.models import Event, EventState
from events.schemas import SignupInputPatch
from events.services import apply_signup_input, resolve_or_create_org_user
from org.models_profiles import PlayerDotaProfile


class ApplySignupInputTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="alice")
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
        )
        self.org_user = resolve_or_create_org_user(self.user, self.org)

    def test_empty_patch_is_noop(self):
        before = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        result = apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            patch=SignupInputPatch(),
        )
        after = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        # Empty patch should NOT create a profile and SHOULD return None.
        self.assertIsNone(result)
        self.assertEqual(after, before)

    def test_writes_friend_id(self):
        apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            patch=SignupInputPatch(unverified_friend_id="12345678"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.unverified_friend_id, "12345678")

    def test_writes_positions_and_dedups(self):
        apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            patch=SignupInputPatch(positions=[1, 3, 3, 5]),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertTrue(profile.pos_1)
        self.assertFalse(profile.pos_2)
        self.assertTrue(profile.pos_3)
        self.assertFalse(profile.pos_4)
        self.assertTrue(profile.pos_5)

    def test_discord_list_input_maps_slot_order_to_priority(self):
        """Discord adapter sends positions as a list ordered by user pick order
        (1st choice / 2nd choice / 3rd choice from sequential Selects). The
        list index + 1 becomes the priority on CustomUser.positions so
        Discord users get actual rankings instead of all-Favorite."""
        from app.models import PositionsModel

        # Ensure user has a PositionsModel to write to.
        self.user.positions = PositionsModel.objects.create()

        apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            # [3, 1, 5] = "offlane is my 1st choice, carry 2nd, hard_support 3rd"
            patch=SignupInputPatch(positions=[3, 1, 5]),
        )
        self.user.refresh_from_db()
        positions = self.user.positions
        self.assertEqual(positions.offlane, 1)  # 1st pick → Favorite
        self.assertEqual(positions.carry, 2)    # 2nd pick → Can play
        self.assertEqual(positions.hard_support, 3)  # 3rd pick → If team needs
        self.assertEqual(positions.mid, 0)
        self.assertEqual(positions.soft_support, 0)

    def test_discord_list_input_duplicate_role_keeps_earliest_slot(self):
        from app.models import PositionsModel

        self.user.positions = PositionsModel.objects.create()

        apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            # [1, 3, 1] — carry appears twice; keep the earliest slot (priority 1).
            patch=SignupInputPatch(positions=[1, 3, 1]),
        )
        self.user.refresh_from_db()
        positions = self.user.positions
        self.assertEqual(positions.carry, 1)
        self.assertEqual(positions.offlane, 2)

    def test_web_dict_input_preserves_user_priorities(self):
        """Web modal sends positions as a {carry, mid, …} dict with the user's
        per-role priorities (matches CustomUser.positions shape). Those values
        land verbatim on PositionsModel without being flattened to 1."""
        from app.models import PositionsModel
        from events.schemas import PositionPriorities

        self.user.positions = PositionsModel.objects.create()

        apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            patch=SignupInputPatch(
                positions=PositionPriorities(
                    carry=1, mid=2, offlane=0, soft_support=4, hard_support=0
                ),
            ),
        )
        self.user.refresh_from_db()
        positions = self.user.positions
        self.assertEqual(positions.carry, 1)
        self.assertEqual(positions.mid, 2)
        self.assertEqual(positions.offlane, 0)
        self.assertEqual(positions.soft_support, 4)
        self.assertEqual(positions.hard_support, 0)
        # Binary pos_N booleans derive from priorities > 0
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertTrue(profile.pos_1)
        self.assertTrue(profile.pos_2)
        self.assertFalse(profile.pos_3)
        self.assertTrue(profile.pos_4)
        self.assertFalse(profile.pos_5)

    def test_rank_status_active_writes(self):
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_status="active"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_status, "active")


    def test_rank_status_disallowed_raises(self):
        self.event.allow_active_mmr = False
        self.event.save()
        with self.assertRaises(DjangoValidationError) as ctx:
            apply_signup_input(
                org_user=self.org_user, event=self.event,
                patch=SignupInputPatch(rank_status="active"),
            )
        self.assertEqual(ctx.exception.code, "rank_status_disallowed")
        self.assertIn("active MMR signups", str(ctx.exception))

    def test_rank_medal_writes(self):
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_medal="Crusader 3"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_medal, "Crusader 3")


    def test_battle_cup_tier_writes(self):
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(battle_cup_tier=5),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.battle_cup_tier, 5)

    def test_rank_screenshot_writes(self):
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/abc.png"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_screenshot, "https://i.imgur.com/abc.png")


    def test_screenshot_bad_shape_raises(self):
        with self.assertRaises(DjangoValidationError) as ctx:
            apply_signup_input(
                org_user=self.org_user, event=self.event,
                patch=SignupInputPatch(rank_screenshot="ftp://example.com/x.png"),
            )
        self.assertEqual(ctx.exception.code, "screenshot_bad_url")


    def test_screenshot_bad_extension_raises(self):
        with self.assertRaises(DjangoValidationError):
            apply_signup_input(
                org_user=self.org_user, event=self.event,
                patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/abc.gif"),
            )


    def test_battlecup_screenshot_writes(self):
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(battlecup_screenshot="https://i.imgur.com/bc.jpg"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.battlecup_screenshot, "https://i.imgur.com/bc.jpg")

    def test_duplicate_friend_id_raises(self):
        # Other-org user owns Friend ID 9999. Global dedup must still reject.
        other_org = Organization.objects.create(name="Other Org")
        bob = CustomUser.objects.create(username="bob")
        bob_org_user = resolve_or_create_org_user(bob, other_org)
        PlayerDotaProfile.objects.create(org_user=bob_org_user, unverified_friend_id="9999")
        with self.assertRaises(DjangoValidationError) as ctx:
            apply_signup_input(
                org_user=self.org_user, event=self.event,
                patch=SignupInputPatch(unverified_friend_id="9999"),
            )
        self.assertEqual(ctx.exception.code, "duplicate_friend_id")
        self.assertIn("9999", str(ctx.exception))
        self.assertIn("dota.kettle.sh", str(ctx.exception))

    def test_multi_call_partial_patch_accumulates(self):
        # Mirror Discord's 4-turn flow: rank_status, then positions, then medal,
        # then screenshot. Each call commits independently; final state has all writes.
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_status="active"),
        )
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(positions=[1, 2]),
        )
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_medal="Legend 4"),
        )
        apply_signup_input(
            org_user=self.org_user, event=self.event,
            patch=SignupInputPatch(rank_screenshot="https://i.imgur.com/x.png"),
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_status, "active")
        self.assertTrue(profile.pos_1 and profile.pos_2)
        self.assertFalse(profile.pos_3)
        self.assertEqual(profile.rank_medal, "Legend 4")
        self.assertEqual(profile.rank_screenshot, "https://i.imgur.com/x.png")


    def test_idempotent_re_application(self):
        patch = SignupInputPatch(rank_status="active", positions=[3])
        apply_signup_input(org_user=self.org_user, event=self.event, patch=patch)
        apply_signup_input(org_user=self.org_user, event=self.event, patch=patch)
        self.assertEqual(
            PlayerDotaProfile.objects.filter(org_user=self.org_user).count(), 1
        )
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_status, "active")
        self.assertTrue(profile.pos_3)

    def test_cacheops_invalidation_after_commit(self):
        # apply_signup_input calls invalidate_after_commit synchronously
        # (not wrapped in transaction.on_commit). With the function patched, the
        # spy receives the call directly under the `with patch(...)` block — no
        # captureOnCommitCallbacks needed.
        with mock_patch("events.services.invalidate_after_commit") as spy:
            apply_signup_input(
                org_user=self.org_user,
                event=self.event,
                patch=SignupInputPatch(rank_status="active"),
            )
        spy.assert_called_once()
        args = spy.call_args.args
        self.assertEqual(len(args), 3)
        # Confirm correct objects were passed (profile, org_user, event), in that order.
        self.assertEqual(args[1], self.org_user)
        self.assertEqual(args[2], self.event)

    def test_rollback_does_not_fire_invalidation(self):
        # Spy on the inner cacheops.invalidate_obj that invalidate_after_commit
        # eventually calls via on_commit. On rollback, the callback is dropped, so
        # invalidate_obj is never called.
        with mock_patch("app.cache_utils.invalidate_obj") as spy:
            try:
                with transaction.atomic():
                    apply_signup_input(
                        org_user=self.org_user,
                        event=self.event,
                        patch=SignupInputPatch(rank_status="active"),
                    )
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
        spy.assert_not_called()
