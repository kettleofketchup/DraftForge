from datetime import timedelta
from django.core.exceptions import ValidationError as DjangoValidationError
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
