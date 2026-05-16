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

from django.db import transaction
from django.test import TestCase
from django.utils import timezone as tz
from app.models import CustomUser, Organization, PositionsModel
from events.models import Event, EventSignup
from org.models import OrgUser
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

    def _signup_with_positions(self, *, pos_1=False, pos_2=False, pos_3=False,
                                pos_4=False, pos_5=False, unverified_friend_id=None):
        """Helper: populate the user's dota profile, create signup, run writethrough.

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
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        from events.services import apply_signup_writethrough
        apply_signup_writethrough(signup)
        signup.refresh_from_db()
        self.user.refresh_from_db()
        return signup

    def test_positions_writethrough_no_longer_runs_here(self):
        """`apply_signup_writethrough` MUST NOT touch User.positions.

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
            pos_1=True, pos_2=True, pos_3=True, pos_4=True, pos_5=True,
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

    def test_user_update_failure_rolls_back(self):
        """If an unprotected write inside `apply_signup_writethrough` fails, a
        caller wrapping `signup.create + writethrough` in `transaction.atomic`
        gets full rollback.

        Post-#217 the writethrough is mostly defensive — the steam_id branch has
        its own `try/except (ValueError, Exception)` to keep a steam-id sync
        failure from blocking signup creation. The one unprotected call near
        the end is `invalidate_after_commit`; patching it to raise tests the
        rollback path realistically. Wrap in atomic to mirror the production
        call pattern (`_create_signup` → `EventSignup.create` → writethrough,
        all inside a transaction).
        """
        from unittest.mock import patch

        with patch(
            "events.services.invalidate_after_commit",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self._signup_with_positions(pos_1=True)

        # No partial state survived — the signup row was rolled back.
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(),
            0,
        )

    def test_signup_create_rolls_back_when_writethrough_fails(self):
        """Spec invariant: signup save + writethrough share one transaction.atomic.

        When a caller wraps EventSignup.objects.create + apply_signup_writethrough
        in the same atomic block, a writethrough failure must roll back the signup
        too. Force the failure at `invalidate_after_commit` (the only unprotected
        write in the writethrough's post-#217 body).
        """
        from unittest.mock import patch
        from events.services import apply_signup_writethrough

        # Pre-create profile so the writethrough proceeds past its early returns.
        PlayerDotaProfile.objects.get_or_create(org_user=self.org_user)

        initial_signup_count = EventSignup.objects.filter(event=self.event).count()

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                signup = EventSignup.objects.create(event=self.event, user=self.user)
                with patch(
                    "events.services.invalidate_after_commit",
                    side_effect=RuntimeError("boom"),
                ):
                    apply_signup_writethrough(signup)

        # Signup AND writethrough rolled back as a unit.
        self.assertEqual(
            EventSignup.objects.filter(event=self.event).count(),
            initial_signup_count,
        )
