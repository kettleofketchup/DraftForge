"""The Friend ID lives on User.steam_account_id: filled once, never replaced
by a signup (#717). Positions and MMR are not touched by the signup itself."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, PositionsModel
from events.constants import SignupStatus
from events.eligibility import claim_friend_id
from events.models import Event, EventSignup
from events.schemas import SignupInputPatch
from events.services import _create_signup, apply_signup_input, process_rsvp
from events.tests.base import EventTestCase
from org.membership import resolve_or_create_org_user
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDotaProfile


class SignupWritethroughTest(TestCase):
    """Regression for #196a — User-level fields must reflect signup-submitted data."""

    def setUp(self):
        self.org = Organization.objects.create(name="WT Org")
        self.user = CustomUser.objects.create(
            username="wt_user",
            positions=PositionsModel.objects.create(),
        )
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)
        self.event = Event.objects.create(
            name="WT Event",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=False,
        )

    def _signup_with_positions(
        self,
        *,
        pos_1=False,
        pos_2=False,
        pos_3=False,
        pos_4=False,
        pos_5=False,
    ):
        """Helper: populate the user's dota profile, then sign up via _create_signup."""
        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=self.org_user)
        profile.pos_1 = pos_1
        profile.pos_2 = pos_2
        profile.pos_3 = pos_3
        profile.pos_4 = pos_4
        profile.pos_5 = pos_5
        profile.save()
        signup = _create_signup(self.event, self.user)
        signup.refresh_from_db()
        self.user.refresh_from_db()
        return signup

    def test_positions_writethrough_no_longer_runs_here(self):
        """The signup Steam sync MUST NOT touch User.positions.

        Position writethrough used to live here (mapping PlayerDotaProfile.pos_N
        booleans to PositionsModel priorities flattened at 1). That was removed in
        PR #217 because it overwrote the real per-role priorities (0..5) that
        users now pick in the web signup modal — those land on user.positions
        directly via `apply_signup_input` BEFORE `_create_signup` runs. Discord
        users with `positions=list[int]` get slot-order-derived priorities
        through the same `apply_signup_input` path. Re-introducing a flatten-
        to-1 here would silently clobber both.
        """
        # Seed user.positions with real priorities (simulating what
        # apply_signup_input wrote during the signup modal flow).
        self.user.positions.carry = 1
        self.user.positions.mid = 2
        self.user.positions.offlane = 3
        self.user.positions.soft_support = 0
        self.user.positions.hard_support = 0
        self.user.positions.save()

        # Signup with PlayerDotaProfile.pos_N flags set. The writethrough
        # would, in the old behavior, have flattened all of these to 1.
        self._signup_with_positions(
            pos_1=True,
            pos_2=True,
            pos_3=True,
            pos_4=True,
            pos_5=True,
        )
        self.user.positions.refresh_from_db()

        # Priorities preserved — writethrough did not touch positions.
        self.assertEqual(self.user.positions.carry, 1)
        self.assertEqual(self.user.positions.mid, 2)
        self.assertEqual(self.user.positions.offlane, 3)
        self.assertEqual(self.user.positions.soft_support, 0)
        self.assertEqual(self.user.positions.hard_support, 0)


class SignupWritethroughInvariantsTest(SignupWritethroughTest):
    """MMR isolation + transaction atomicity (#196a)."""

    def test_mmr_is_not_touched_on_signup_save(self):
        # Set OrgUser.mmr to a known value
        self.org_user.mmr = 4500
        self.org_user.save(update_fields=["mmr"])

        # Signup with a different "submitted" MMR on the profile
        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=self.org_user)
        profile.mmr = 1000
        profile.save()

        self._signup_with_positions(pos_1=True)
        self.org_user.refresh_from_db()
        # OrgUser MMR untouched — only approve_signup(mmr_override=...) writes it.
        self.assertEqual(self.org_user.mmr, 4500)

    def test_signup_input_rolls_back_with_the_signup(self):
        with patch(
            "events.services.invalidate_after_commit",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    apply_signup_input(
                        org_user=self.org_user,
                        event=self.event,
                        patch=SignupInputPatch(steam_account_id="56565"),
                    )
                    _create_signup(self.event, self.user)

        self.assertFalse(
            EventSignup.objects.filter(event=self.event, user=self.user).exists()
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.steam_account_id)


class ClaimFriendIdTest(EventTestCase):
    def _assert_refused(self, user: CustomUser, fid: str, code: str) -> None:
        with self.assertRaises(ValidationError) as ctx:
            claim_friend_id(user, fid)
        self.assertEqual(ctx.exception.code, code)

    def test_fills_an_empty_id(self) -> None:
        user = self.make_user()
        self.assertEqual(claim_friend_id(user, " 0424242 "), 424242)
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 424242)
        self.assertEqual(user.steamid, 424242 + CustomUser.STEAM_ID_64_BASE)

    def test_accepts_ids_above_signed_32_bit(self) -> None:
        user = self.make_user()
        self.assertEqual(claim_friend_id(user, str(2**32 - 1)), 2**32 - 1)
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 2**32 - 1)

    def test_same_id_is_a_no_op(self) -> None:
        user = self.make_user()
        user.steam_account_id = 99999
        user.save()
        with self.assertNumQueries(0):
            self.assertIsNone(claim_friend_id(user, "099999"))

    def test_blank_is_a_no_op(self) -> None:
        user = self.make_user()
        user.steam_account_id = 99999
        user.save()
        self.assertIsNone(claim_friend_id(user, "  "))
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 99999)

    def test_different_id_is_refused(self) -> None:
        user = self.make_user()
        user.steam_account_id = 99999
        user.save()
        self._assert_refused(user, "12345", "friend_id_already_set")
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 99999)

    def test_id_held_by_another_user_is_refused(self) -> None:
        other = self.make_user()
        other.steam_account_id = 3000000000
        other.save()
        user = self.make_user()
        self._assert_refused(user, "3000000000", "duplicate_friend_id")
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_malformed_or_out_of_range_ids_are_refused(self) -> None:
        user = self.make_user()
        for fid in ("abc", "12a", "0", "000", str(2**32), "9" * 21, "\u0661\u0662"):
            with self.subTest(fid=fid):
                self._assert_refused(user, fid, "invalid_friend_id")
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_race_on_the_unique_column_is_refused_and_keeps_the_transaction(
        self,
    ) -> None:
        other = self.make_user()
        other.steam_account_id = 111111
        other.save()
        user = self.make_user()
        with transaction.atomic():
            with patch(
                "events.eligibility.steam.steam_account_id_holder", return_value=None
            ):
                self._assert_refused(user, "111111", "duplicate_friend_id")
            self.assertIsNone(user.steam_account_id)
            self.assertTrue(CustomUser.objects.filter(pk=user.pk).exists())
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)


class SignupInputFriendIdTest(EventTestCase):
    def _apply(self, user: CustomUser, fid: str) -> None:
        apply_signup_input(
            org_user=resolve_or_create_org_user(user, self.org),
            event=self.make_event(),
            patch=SignupInputPatch(steam_account_id=fid),
        )

    def test_fills_the_user_not_the_profile(self) -> None:
        user = self.make_user()
        self._apply(user, "525252")
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 525252)

    def test_refused_change_writes_nothing(self) -> None:
        user = self.make_user()
        user.steam_account_id = 99999
        user.save()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        with self.assertRaises(ValidationError):
            self._apply(user, "12345")
        self.assertFalse(PlayerDotaProfile.objects.filter(org_user=org_user).exists())
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 99999)

    def test_rsvp_after_input_sees_the_new_id(self) -> None:
        ev = self.make_event(require_steam_id=True)
        user = self.make_user()
        apply_signup_input(
            org_user=resolve_or_create_org_user(user, self.org),
            event=ev,
            patch=SignupInputPatch(steam_account_id="535353"),
        )
        signup = process_rsvp(ev, user)
        self.assertEqual(signup.status, SignupStatus.APPROVED)
