"""Test signup-side writethrough to User-level fields (#196a).

Signup writes PlayerDotaProfile.pos_1..5 and an unverified_friend_id (32-bit Steam
account ID). We mirror those to User.positions (last-write-wins) and
User.steam_account_id (first-write-wins).

NOTE: PlayerDotaProfile does NOT have a steam_account_id field directly — it has
unverified_friend_id (a CharField on PlayerProfileMixin). The writethrough therefore
reads profile.unverified_friend_id (a non-empty string of digits) and writes it as
an integer to User.steam_account_id (IntegerField, first-write-wins).

MMR is NOT touched on signup save — it continues through MmrApprovalModal /
approve_signup(mmr_override=...).
"""

from collections.abc import Callable
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser, Organization, PositionsModel
from events.constants import SignupStatus
from events.eligibility import sync_steam_account_from_profiles
from events.models import Event, EventSignup
from events.schemas import SignupInputPatch
from events.services import (
    _create_signup,
    apply_signup_input,
    cancel_signup,
    process_rsvp,
)
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile


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
        unverified_friend_id=None,
    ):
        """Helper: populate the user's dota profile, then sign up via _create_signup.

        Uses unverified_friend_id (the actual PlayerDotaProfile/PlayerProfileMixin
        field) instead of steam_account_id which does not exist on that model.
        """
        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=self.org_user)
        profile.pos_1 = pos_1
        profile.pos_2 = pos_2
        profile.pos_3 = pos_3
        profile.pos_4 = pos_4
        profile.pos_5 = pos_5
        if unverified_friend_id is not None:
            profile.unverified_friend_id = str(unverified_friend_id)
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


class SignupSteamIdWritethroughTest(SignupWritethroughTest):
    """First-write-wins on User.steam_account_id (identity-bearing, unique=True).

    Source: profile.unverified_friend_id (CharField of digits on PlayerProfileMixin).
    Target: User.steam_account_id (IntegerField, unique=True, first-write-wins).
    """

    def test_steam_id_set_when_user_has_none(self):
        self.assertIsNone(self.user.steam_account_id)
        self._signup_with_positions(unverified_friend_id=12345)
        self.assertEqual(self.user.steam_account_id, 12345)

    def test_steam_id_preserved_when_user_already_has_one(self):
        self.user.steam_account_id = 99999
        self.user.save(update_fields=["steam_account_id"])
        self._signup_with_positions(unverified_friend_id=12345)
        self.user.refresh_from_db()
        # First-write-wins: existing 99999 preserved, signup 12345 ignored.
        self.assertEqual(self.user.steam_account_id, 99999)


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

    def test_signup_rolls_back_when_a_later_step_fails(self):
        """The Steam sync and the signup row share _create_signup's atomic
        block: a failure after the sync rolls both back."""
        PlayerDotaProfile.objects.update_or_create(
            org_user=self.org_user, defaults={"unverified_friend_id": "56565"}
        )
        with patch(
            "events.services.invalidate_after_commit",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                _create_signup(self.event, self.user)

        self.assertFalse(
            EventSignup.objects.filter(event=self.event, user=self.user).exists()
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.steam_account_id)


class SyncSteamAccountFromProfilesTest(EventTestCase):
    def _user_with_friend_id(self, fid: str) -> CustomUser:
        user = self.make_user()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        PlayerDotaProfile.objects.update_or_create(
            org_user=org_user, defaults={"unverified_friend_id": fid}
        )
        return CustomUser.objects.get(pk=user.pk)

    def _skips(self, logs: list[dict[str, object]]) -> list[dict[str, object]]:
        return [e for e in logs if e["event"] == "signup_steam_writethrough_skipped"]

    def test_writes_friend_id_and_reports_it(self) -> None:
        user = self._user_with_friend_id("424242")
        self.assertTrue(sync_steam_account_from_profiles(user, self.org))
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 424242)

    def test_reads_deadlock_profile_when_dota_has_none(self) -> None:
        user = self.make_user()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        PlayerDeadlockProfile.objects.update_or_create(
            org_user=org_user, defaults={"unverified_friend_id": "434343"}
        )
        user = CustomUser.objects.get(pk=user.pk)
        self.assertTrue(sync_steam_account_from_profiles(user, self.org))
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 434343)

    def test_race_conflict_logs_and_leaves_user_unchanged(self) -> None:
        user = self._user_with_friend_id("111111")
        other = self.make_user()
        other.steam_account_id = 111111
        other.save()
        with transaction.atomic():
            with capture_logs() as logs:
                wrote = sync_steam_account_from_profiles(user, self.org, event_id=77)
            self.assertEqual(EventSignup.objects.filter(user=user).count(), 0)
        self.assertFalse(wrote)
        skips = self._skips(logs)
        self.assertEqual(len(skips), 1)
        self.assertEqual(skips[0]["reason"], "conflict")
        self.assertEqual(skips[0]["conflicting_user_id"], other.pk)
        self.assertEqual(skips[0]["user_id"], user.pk)
        self.assertEqual(skips[0]["event_id"], 77)
        self.assertEqual(skips[0]["log_level"], "warning")
        self.assertIsNone(user.steam_account_id)
        self.assertIsNone(user.steamid)
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_out_of_range_friend_id_skips(self) -> None:
        user = self._user_with_friend_id("9" * 20)
        with capture_logs() as logs:
            self.assertFalse(sync_steam_account_from_profiles(user, self.org))
        self.assertEqual(self._skips(logs)[0]["reason"], "out_of_range")
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_non_numeric_friend_id_skips(self) -> None:
        user = self._user_with_friend_id("abc")
        with capture_logs() as logs:
            self.assertFalse(sync_steam_account_from_profiles(user, self.org))
        self.assertEqual(self._skips(logs)[0]["reason"], "non_numeric")

    def test_existing_account_id_is_kept(self) -> None:
        user = self._user_with_friend_id("454545")
        user.steam_account_id = 99999
        user.save()
        self.assertFalse(sync_steam_account_from_profiles(user, self.org))
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 99999)

    def test_event_without_org_skips(self) -> None:
        user = self._user_with_friend_id("464646")
        with self.assertNumQueries(0):
            self.assertFalse(sync_steam_account_from_profiles(user, None))
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)


class SignupSteamSyncOrderingTest(EventTestCase):
    """The Steam account is written once per signup, before the status is decided."""

    def _user_with_friend_id(self, fid: str) -> CustomUser:
        user = self.make_user()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        PlayerDotaProfile.objects.update_or_create(
            org_user=org_user, defaults={"unverified_friend_id": fid}
        )
        return CustomUser.objects.get(pk=user.pk)

    def _skips(self, logs: list[dict[str, object]]) -> list[dict[str, object]]:
        return [e for e in logs if e["event"] == "signup_steam_writethrough_skipped"]

    def _recording_check(self, seen: list[int | None]) -> Callable[..., list]:
        def record(event: Event, user: CustomUser, **_kwargs: object) -> list:
            seen.append(user.steam_account_id)
            return []

        return record

    def test_conflicting_friend_id_logs_once_and_waits_for_approval(self) -> None:
        ev = self.make_event(require_steam_id=True)
        user = self._user_with_friend_id("515151")
        other = self.make_user()
        other.steam_account_id = 515151
        other.save()
        with capture_logs() as logs:
            signup = process_rsvp(ev, user)
        skips = self._skips(logs)
        self.assertEqual(len(skips), 1, skips)
        self.assertEqual(skips[0]["reason"], "conflict")
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)

    def test_process_rsvp_writes_steam_account_before_requirements(self) -> None:
        ev = self.make_event(require_steam_id=True)
        user = self._user_with_friend_id("525252")
        seen: list[int | None] = []
        with patch(
            "events.services.unmet_codes",
            side_effect=self._recording_check(seen),
        ):
            process_rsvp(ev, user)
        self.assertEqual(seen, [525252])

    def test_promotion_writes_steam_account_before_requirements(self) -> None:
        ev = self.make_event(require_steam_id=True, max_players=1)
        holder = process_rsvp(ev, self.make_user(steamid=76561198000005353))
        waiting_user = self.make_user()
        waiting = process_rsvp(ev, waiting_user)
        self.assertEqual(waiting.status, SignupStatus.WAITLISTED)
        PlayerDotaProfile.objects.update_or_create(
            org_user=OrgUser.objects.get(user=waiting_user, organization=self.org),
            defaults={"unverified_friend_id": "535353"},
        )
        seen: list[int | None] = []
        with patch(
            "events.services.unmet_codes",
            side_effect=self._recording_check(seen),
        ):
            cancel_signup(holder)
        self.assertEqual(seen, [535353])
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, SignupStatus.APPROVED)

    def test_conflict_after_validation_keeps_outer_transaction_usable(self) -> None:
        ev = self.make_event(require_steam_id=True)
        user = self.make_user()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        apply_signup_input(
            org_user=org_user,
            event=ev,
            patch=SignupInputPatch(unverified_friend_id="111111"),
        )
        other = self.make_user()
        other.steam_account_id = 111111
        other.save()
        with transaction.atomic():
            with capture_logs() as logs:
                signup = process_rsvp(ev, user)
            self.assertTrue(EventSignup.objects.filter(pk=signup.pk).exists())
        skips = self._skips(logs)
        self.assertEqual(len(skips), 1, skips)
        self.assertEqual(skips[0]["reason"], "conflict")
        self.assertEqual(skips[0]["conflicting_user_id"], other.pk)
        self.assertIsNone(user.steam_account_id)
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)
