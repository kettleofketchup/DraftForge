from itertools import product
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, Tournament
from events.constants import EventState, SignupStatus
from events.discord.providers.dota import _check_dota_profile_complete
from events.eligibility import (
    REQUIREMENT_CHECKS,
    UNMET_LABELS,
    Unmet,
    claim_friend_id,
    has_steam_id,
    precheck_friend_id,
    refresh_unmet_requirements,
    unmet_requirements,
    validate_friend_id,
)
from events.models import Event, EventSignup
from events.schemas import DotaModalConfig, SignupInputPatch, dota_require_screenshot
from events.serializers import EventSignupSerializer
from events.services import (
    apply_signup_input,
    approve_signup,
    cancel_signup,
    process_rsvp,
    reinstate_signup,
)
from events.tests.base import EventTestCase
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDotaProfile
from steam.services.account_lookup import SteamLookupRateLimited, cached_exists_key

SCREENSHOT_CODES = {Unmet.RANK_SCREENSHOT_MISSING, Unmet.BATTLECUP_SCREENSHOT_MISSING}


class EligibilityMatrixTests(EventTestCase):
    def _org_user(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=self.org)

    def _declared(self, user: CustomUser, rank_status: str, **fields: object) -> None:
        profile, _ = PlayerDotaProfile.objects.get_or_create(
            org_user=self._org_user(user)
        )
        profile.declare_rank(rank_status)
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.save()

    def test_no_profile_with_gate_is_undeclared(self) -> None:
        ev = self.make_event(allow_battlecup_rating=False)
        u = self.make_user()
        self.assertEqual(unmet_requirements(ev, u), [Unmet.DOTA_RANK_UNDECLARED])

    def test_default_row_from_friend_id_patch_is_undeclared(self) -> None:
        ev = self.make_event()
        ev_with_min_mmr = self.make_event(min_mmr=3000)
        u = self.make_user()
        ou = self._org_user(u)
        apply_signup_input(
            org_user=ou,
            event=ev,
            patch=SignupInputPatch(steam_account_id="123456"),
        )
        self.assertTrue(PlayerDotaProfile.objects.filter(org_user=ou).exists())
        self.assertIn(
            Unmet.DOTA_RANK_UNDECLARED, unmet_requirements(ev_with_min_mmr, u)
        )

    def test_every_single_gate_fails_closed_without_profile(self) -> None:
        gates: list[dict[str, object]] = [
            {"allow_active_mmr": False},
            {"allow_previous_rank": False},
            {"allow_battlecup_rating": False},
            {"discord_require_rank_screenshot": True},
            {"discord_require_battlecup_screenshot": True},
            {"min_mmr": 3000},
        ]
        for gate in gates:
            with self.subTest(**gate):
                ev = self.make_event(**gate)
                u = self.make_user()
                self.assertEqual(
                    unmet_requirements(ev, u), [Unmet.DOTA_RANK_UNDECLARED]
                )

    def test_unknown_declared_status_counts_as_undeclared(self) -> None:
        gated = self.make_event(min_mmr=3000)
        open_event = self.make_event()
        u = self.make_user()
        PlayerDotaProfile.objects.create(
            org_user=self._org_user(u),
            rank_status="x",
            rank_declared_at=gated.scheduled_at,
        )
        self.assertEqual(unmet_requirements(gated, u), [Unmet.DOTA_RANK_UNDECLARED])
        self.assertEqual(unmet_requirements(open_event, u), [])

    def test_unknown_status_is_not_an_allowed_rank_type(self) -> None:
        cfg = DotaModalConfig.from_event(self.make_event())
        self.assertFalse(cfg.allows_rank_status("x"))

    def test_signup_input_rank_status_declares(self) -> None:
        ev = self.make_event(min_mmr=3000)
        u = self.make_user()
        ou = self._org_user(u)
        apply_signup_input(
            org_user=ou, event=ev, patch=SignupInputPatch(rank_status="never")
        )
        profile = PlayerDotaProfile.objects.get(org_user=ou)
        self.assertIsNotNone(profile.rank_declared_at)
        self.assertEqual(unmet_requirements(ev, u), [])

    def test_no_gate_no_profile_passes(self) -> None:
        ev = self.make_event()
        u = self.make_user()
        self.assertEqual(unmet_requirements(ev, u), [])

    def test_matrix(self) -> None:
        cases: list[tuple[str, dict[str, object], str, dict[str, object], list]] = [
            (
                "active below min_mmr",
                {"min_mmr": 3000},
                "active",
                {"mmr": 2000},
                [Unmet.BELOW_MIN_MMR],
            ),
            (
                "active above min_mmr",
                {"min_mmr": 3000},
                "active",
                {"mmr": 4000},
                [],
            ),
            (
                "previous disallowed",
                {"allow_previous_rank": False},
                "previous",
                {},
                [Unmet.RANK_TYPE_DISALLOWED],
            ),
            (
                "previous needs no rank screenshot",
                {"discord_require_rank_screenshot": True},
                "previous",
                {},
                [],
            ),
            (
                "active without rank screenshot",
                {"discord_require_rank_screenshot": True},
                "active",
                {},
                [Unmet.RANK_SCREENSHOT_MISSING],
            ),
            (
                "active with rank screenshot",
                {"discord_require_rank_screenshot": True},
                "active",
                {"rank_screenshot": "https://x.test/r.png"},
                [],
            ),
            (
                "never without battlecup screenshot",
                {"discord_require_battlecup_screenshot": True},
                "never",
                {},
                [Unmet.BATTLECUP_SCREENSHOT_MISSING],
            ),
            (
                "never ignores min_mmr",
                {"min_mmr": 3000},
                "never",
                {},
                [],
            ),
        ]
        for label, gates, rank_status, fields, expected in cases:
            with self.subTest(label):
                ev = self.make_event(**gates)
                u = self.make_user()
                self._declared(u, rank_status, **fields)
                self.assertEqual(unmet_requirements(ev, u), expected)

    def test_screenshot_parity(self) -> None:
        for rank_status, (rank_req, bc_req) in product(
            ("active", "previous", "never"), product([True, False], [True, False])
        ):
            with self.subTest(rank_status=rank_status, rank=rank_req, bc=bc_req):
                ev = self.make_event(
                    discord_require_rank_screenshot=rank_req,
                    discord_require_battlecup_screenshot=bc_req,
                )
                u = self.make_user()
                self._declared(u, rank_status)
                codes = set(unmet_requirements(ev, u))
                self.assertEqual(
                    bool(codes & SCREENSHOT_CODES),
                    dota_require_screenshot(
                        rank_status, DotaModalConfig.from_event(ev)
                    ),
                )

    def test_deadlock_event_ignores_dota_profile(self) -> None:
        ev = self.make_event(
            game_type=GameType.DEADLOCK,
            require_mmr_verified=True,
            allow_active_mmr=False,
            min_mmr=9000,
            discord_require_rank_screenshot=True,
        )
        u = self.make_user()
        self._declared(u, "active", mmr=100)
        ou = self._org_user(u)
        self.assertFalse(ou.has_active_dota_mmr)
        self.assertEqual(unmet_requirements(ev, u), [])

    def test_dota_event_mmr_unverified(self) -> None:
        ev = self.make_event(require_mmr_verified=True)
        u = self.make_user()
        self.assertEqual(unmet_requirements(ev, u), [Unmet.MMR_UNVERIFIED])

    def test_registry_covers_every_game_type(self) -> None:
        self.assertEqual(set(REQUIREMENT_CHECKS), set(GameType))

    def test_labels_cover_every_code(self) -> None:
        self.assertEqual(set(UNMET_LABELS), set(Unmet))

    def test_has_steam_id_reads_the_user(self) -> None:
        u = self.make_user()
        PlayerDotaProfile.objects.create(org_user=self._org_user(u))
        self.assertFalse(has_steam_id(u))
        u.steam_account_id = 2**32 - 1
        u.save()
        self.assertTrue(has_steam_id(u))

    def test_require_steam_id_met_by_user_friend_id(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        u.steam_account_id = 888888
        u.save()
        self.assertEqual(unmet_requirements(ev, u), [])

    def test_profile_incomplete(self) -> None:
        ev = self.make_event(require_profile_complete=True)
        u = self.make_user(steamid=76561198000123456)
        self.assertEqual(unmet_requirements(ev, u), [Unmet.PROFILE_INCOMPLETE])

    def test_event_without_org(self) -> None:
        # Event.organization is NOT NULL in the schema; an unsaved instance
        # still exercises the org_user=None path.
        ev = Event(
            organization=None,
            name="Orgless",
            scheduled_at=self.event.scheduled_at,
            state=self.event.state,
            created_by=self.admin,
            require_steam_id=True,
        )
        with_steam = self.make_user(steamid=76561198000654321)
        without_steam = self.make_user()
        self.assertEqual(unmet_requirements(ev, with_steam), [])
        self.assertEqual(
            unmet_requirements(ev, without_steam), [Unmet.STEAM_ID_MISSING]
        )


class DiscordProfileCompleteTests(EventTestCase):
    def test_undeclared_row_is_not_complete(self) -> None:
        u = self.make_user()
        ou = OrgUser.objects.get(user=u, organization=self.org)
        profile = PlayerDotaProfile.objects.create(
            org_user=ou, rank_status="active", rank_medal="Herald 1", pos_1=True
        )
        self.assertFalse(_check_dota_profile_complete(ou, self.event))
        profile.declare_rank("active")
        profile.save()
        ou = OrgUser.objects.get(pk=ou.pk)
        self.assertTrue(_check_dota_profile_complete(ou, self.event))


class ValidateFriendIdTests(EventTestCase):
    def test_leading_zero_and_whitespace_collide_by_value(self) -> None:
        other = self.make_user()
        other.steam_account_id = 123
        other.save()
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id(" 0123 ", self.make_user())
        self.assertEqual(cm.exception.code, "duplicate_friend_id")

    def test_returns_canonical_value(self) -> None:
        self.assertEqual(validate_friend_id(" 00424242 ", self.make_user()), 424242)

    def test_own_steam_account_id_is_a_no_op(self) -> None:
        u = self.make_user()
        u.steam_account_id = 31337
        u.save()
        self.assertIsNone(validate_friend_id("31337", u))

    def test_other_id_than_the_stored_one_is_refused(self) -> None:
        u = self.make_user()
        u.steam_account_id = 31337
        u.save()
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("31338", u)
        self.assertEqual(cm.exception.code, "friend_id_already_set")
        self.assertIn("31337", cm.exception.messages[0])

    def test_range_and_length_boundaries(self) -> None:
        u = self.make_user()
        for fid, expected in (("1", 1), (str(2**31), 2**31), ("0" * 19 + "7", 7)):
            with self.subTest(fid=fid):
                self.assertEqual(validate_friend_id(fid, u), expected)
        for fid in ("0", str(2**32), "9" * 20, "9" * 21):
            with self.subTest(fid=fid):
                with self.assertRaises(DjangoValidationError) as cm:
                    validate_friend_id(fid, u)
                self.assertEqual(cm.exception.code, "invalid_friend_id")

    def test_non_numeric_is_invalid(self) -> None:
        u = self.make_user()
        for fid in ("abc", "12a", "\u0661\u0662\u0663"):
            with self.subTest(fid=fid):
                with self.assertRaises(DjangoValidationError) as cm:
                    validate_friend_id(fid, u)
                self.assertEqual(cm.exception.code, "invalid_friend_id")

    @override_settings(SITE_URL="https://events.example.test")
    def test_duplicate_message_points_at_site_url(self) -> None:
        other = self.make_user()
        other.steam_account_id = 454545
        other.save()
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("454545", self.make_user())
        self.assertIn("https://events.example.test", cm.exception.messages[0])
        self.assertNotIn("dota.kettle.sh", cm.exception.messages[0])


LOOKUP_ON = override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
ENSURE = "events.eligibility.steam.ensure_steam_account_exists"


@LOOKUP_ON
class PrecheckFriendIdTests(EventTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_precheck_not_found_raises(self) -> None:
        with patch(ENSURE, return_value=False):
            with self.assertRaises(DjangoValidationError) as cm:
                precheck_friend_id("424242", self.make_user())
        self.assertEqual(cm.exception.code, "steam_account_not_found")
        self.assertEqual(
            cm.exception.messages[0],
            "No Steam account has Friend ID 424242. Check the number on your "
            "Dota 2 profile or Steam friends page.",
        )

    def test_precheck_lookup_none_accepts(self) -> None:
        with patch(ENSURE, return_value=None):
            self.assertEqual(precheck_friend_id("424242", self.make_user()), 424242)
        with patch(ENSURE, return_value=True):
            self.assertEqual(precheck_friend_id("424243", self.make_user()), 424243)

    def test_precheck_rate_limited_code(self) -> None:
        with patch(ENSURE, side_effect=SteamLookupRateLimited):
            with self.assertRaises(DjangoValidationError) as cm:
                precheck_friend_id("424242", self.make_user())
        self.assertEqual(cm.exception.code, "steam_lookup_rate_limited")
        self.assertEqual(
            cm.exception.messages[0], "Too many Friend ID checks. Try again in an hour."
        )

    def test_precheck_budget_user_charged_not_target(self) -> None:
        user = self.make_user()
        with patch(ENSURE, return_value=True) as ensure:
            precheck_friend_id("424242", user, budget_user=self.admin)
        ensure.assert_called_once_with(424242, budget_user=self.admin)
        with patch(ENSURE, return_value=True) as ensure:
            precheck_friend_id("424242", user)
        ensure.assert_called_once_with(424242, budget_user=user)

    def test_precheck_same_id_no_lookup(self) -> None:
        user = self.make_user()
        user.steam_account_id = 777
        user.save()
        with patch(ENSURE) as ensure:
            self.assertIsNone(precheck_friend_id(" 0777 ", user))
            self.assertIsNone(precheck_friend_id("777", user, allow_change=True))
        ensure.assert_not_called()

    def test_precheck_malformed_no_lookup(self) -> None:
        with patch(ENSURE) as ensure:
            for fid in ("abc", "0", str(2**32)):
                with self.subTest(fid=fid):
                    with self.assertRaises(DjangoValidationError) as cm:
                        precheck_friend_id(fid, self.make_user())
                    self.assertEqual(cm.exception.code, "invalid_friend_id")
        ensure.assert_not_called()

    def test_precheck_duplicate_no_lookup(self) -> None:
        other = self.make_user()
        other.steam_account_id = 515151
        other.save()
        with patch(ENSURE) as ensure:
            with self.assertRaises(DjangoValidationError) as cm:
                precheck_friend_id("515151", self.make_user())
        self.assertEqual(cm.exception.code, "duplicate_friend_id")
        ensure.assert_not_called()

    def test_precheck_already_set_no_lookup_unless_allow_change(self) -> None:
        user = self.make_user()
        user.steam_account_id = 777
        user.save()
        with patch(ENSURE, return_value=True) as ensure:
            with self.assertRaises(DjangoValidationError) as cm:
                precheck_friend_id("778", user)
            self.assertEqual(cm.exception.code, "friend_id_already_set")
            ensure.assert_not_called()
            self.assertEqual(precheck_friend_id("778", user, allow_change=True), 778)
        ensure.assert_called_once_with(778, budget_user=user)

    def test_precheck_strips_and_normalises(self) -> None:
        with patch(ENSURE, return_value=True) as ensure:
            self.assertEqual(precheck_friend_id(" 0123 ", self.make_user()), 123)
        self.assertEqual(ensure.call_args.args, (123,))

    def test_precheck_blank_is_no_op(self) -> None:
        with patch(ENSURE) as ensure:
            self.assertIsNone(precheck_friend_id("  ", self.make_user()))
            self.assertIsNone(precheck_friend_id(None, self.make_user()))
        ensure.assert_not_called()


@LOOKUP_ON
class ValidateFriendIdExistsTests(EventTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_validate_inside_atomic_is_cache_only(self) -> None:
        user = self.make_user()
        with patch("steam.services.account_lookup.SteamAPI") as api:
            cache.set(cached_exists_key(606060), False)
            with self.assertRaises(DjangoValidationError) as cm:
                validate_friend_id("606060", user)
            self.assertEqual(cm.exception.code, "steam_account_not_found")
            self.assertIn("606060", cm.exception.messages[0])
            self.assertEqual(validate_friend_id("606061", user), 606061)
            cache.set(cached_exists_key(606062), True)
            self.assertEqual(validate_friend_id("606062", user), 606062)
        api.assert_not_called()

    def test_validate_check_exists_false_ignores_cache(self) -> None:
        cache.set(cached_exists_key(606060), False)
        self.assertEqual(
            validate_friend_id("606060", self.make_user(), check_exists=False), 606060
        )

    def test_validate_allow_change_permits_change(self) -> None:
        u = self.make_user()
        u.steam_account_id = 31337
        u.save()
        self.assertEqual(validate_friend_id("31338", u, allow_change=True), 31338)

    def test_duplicate_message_mentions_organizer(self) -> None:
        other = self.make_user()
        other.steam_account_id = 454546
        other.save()
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("454546", self.make_user())
        self.assertIn(
            "If this is your account, contact an organizer.", cm.exception.messages[0]
        )


@LOOKUP_ON
class ClaimFriendIdVerificationTests(EventTestCase):
    def setUp(self) -> None:
        cache.clear()

    def _self_signed_up_user(self) -> CustomUser:
        user = self.make_user()
        signup = process_rsvp(self.event, user)
        self.assertTrue(signup.self_made)
        user.refresh_from_db()
        return user

    def test_claim_sets_exists_checked_when_cached_true(self) -> None:
        user = self.make_user()
        cache.set(cached_exists_key(707070), True)
        self.assertEqual(claim_friend_id(user, "707070"), 707070)
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 707070)
        self.assertIsNotNone(user.steam_account_exists_checked_at)
        self.assertFalse(user.steam_account_verified)

    def test_claim_without_cache_leaves_exists_checked_empty(self) -> None:
        user = self.make_user()
        self.assertEqual(claim_friend_id(user, "707071"), 707071)
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_exists_checked_at)

    def test_claim_cached_false_refused(self) -> None:
        user = self.make_user()
        cache.set(cached_exists_key(707072), False)
        with self.assertRaises(DjangoValidationError) as cm:
            claim_friend_id(user, "707072")
        self.assertEqual(cm.exception.code, "steam_account_not_found")
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_claim_verified_by_trusted_staff_verifies(self) -> None:
        user = self._self_signed_up_user()
        cache.set(cached_exists_key(717171), False)
        self.assertEqual(
            claim_friend_id(user, "717171", verified_by=self.admin), 717171
        )
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 717171)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, self.admin.pk)
        self.assertEqual(user.steam_account_verified_org_id, self.org.pk)

    def test_claim_verified_by_self_does_not(self) -> None:
        user = self._self_signed_up_user()
        self.assertEqual(claim_friend_id(user, "727272", verified_by=user), 727272)
        user.refresh_from_db()
        self.assertEqual(user.steam_account_id, 727272)
        self.assertFalse(user.steam_account_verified)

    def test_claim_verified_by_untrusted_does_not(self) -> None:
        user = self._self_signed_up_user()
        cache.set(cached_exists_key(737373), False)
        with self.assertRaises(DjangoValidationError) as cm:
            claim_friend_id(user, "737373", verified_by=self.unrelated_user)
        self.assertEqual(cm.exception.code, "steam_account_not_found")
        self.assertEqual(
            claim_friend_id(user, "737374", verified_by=self.unrelated_user), 737374
        )
        user.refresh_from_db()
        self.assertFalse(user.steam_account_verified)


@patch("events.services.notify_signup_changed")
class UnmetRequirementsPersistenceTests(EventTestCase):
    def _org_user(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=self.org)

    def _declared(self, user: CustomUser, rank_status: str, **fields: object) -> None:
        profile, _ = PlayerDotaProfile.objects.get_or_create(
            org_user=self._org_user(user)
        )
        profile.declare_rank(rank_status)
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.save()

    def _screenshot_event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "auto_approve": False,
            "discord_require_rank_screenshot": True,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def test_manual_approval_signup_stores_codes(self, _notify: MagicMock) -> None:
        ev = self._screenshot_event()
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = process_rsvp(ev, u)
        self.assertEqual(s.status, SignupStatus.RSVP)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [Unmet.RANK_SCREENSHOT_MISSING.value])

    def test_auto_approve_signup_stores_codes(self, _notify: MagicMock) -> None:
        ev = self.make_event(min_mmr=3000)
        s = process_rsvp(ev, self.make_user())
        self.assertEqual(s.status, SignupStatus.PENDING_APPROVAL)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])

    def test_eligible_signup_stores_no_codes(self, _notify: MagicMock) -> None:
        s = process_rsvp(self.make_event(), self.make_user())
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [])

    def test_waitlisted_signup_stores_codes(self, _notify: MagicMock) -> None:
        ev = self.make_event(min_mmr=3000, max_players=1)
        EventSignup.objects.create(
            event=ev, user=self.make_user(), status=SignupStatus.APPROVED
        )
        s = process_rsvp(ev, self.make_user())
        self.assertEqual(s.status, SignupStatus.WAITLISTED)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])

    def test_uploading_screenshot_clears_code(self, _notify: MagicMock) -> None:
        ev = self._screenshot_event()
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = process_rsvp(ev, u)
        EventSignup.objects.get(pk=s.pk).unmet_requirements  # warm the cache
        with self.captureOnCommitCallbacks(execute=True):
            apply_signup_input(
                org_user=self._org_user(u),
                event=ev,
                patch=SignupInputPatch(
                    rank_screenshot="https://cdn.discordapp.com/x.png"
                ),
            )
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [])
        self.assertEqual(s.status, SignupStatus.RSVP)
        self.assertEqual(EventSignup.objects.get(pk=s.pk).unmet_requirements, [])

    def test_refresh_skips_terminal_and_other_org_signups(
        self, _notify: MagicMock
    ) -> None:
        u = self.make_user()
        gated = self.make_event(min_mmr=3000)
        other_org = Organization.objects.create(name="Other Unmet Org")
        other_event = self.make_event(organization=other_org, min_mmr=3000)
        confirmed = EventSignup.objects.create(
            event=gated, user=u, status=SignupStatus.CONFIRMED
        )
        elsewhere = EventSignup.objects.create(
            event=other_event, user=u, status=SignupStatus.RSVP
        )
        changed = refresh_unmet_requirements(self._org_user(u))
        self.assertEqual(changed, 0)
        confirmed.refresh_from_db()
        elsewhere.refresh_from_db()
        self.assertEqual(confirmed.unmet_requirements, [])
        self.assertEqual(elsewhere.unmet_requirements, [])

    def test_refresh_returns_rows_changed(self, _notify: MagicMock) -> None:
        u = self.make_user()
        gated = self.make_event(min_mmr=3000)
        pending = EventSignup.objects.create(
            event=gated, user=u, status=SignupStatus.PENDING_APPROVAL
        )
        ou = self._org_user(u)
        self.assertEqual(refresh_unmet_requirements(ou), 1)
        self.assertEqual(refresh_unmet_requirements(ou), 0)
        pending.refresh_from_db()
        self.assertEqual(pending.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])

    def test_profile_endpoint_refreshes_codes(self, _notify: MagicMock) -> None:
        ev = self._screenshot_event()
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = process_rsvp(ev, u)
        api = APIClient()
        api.force_authenticate(self.admin)
        resp = api.patch(
            f"/api/organizations/{self.org.pk}/users/{u.pk}/dota-profile/update/",
            {"rank_screenshot": "https://cdn.discordapp.com/x.png"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [])

    def test_approve_clears(self, _notify: MagicMock) -> None:
        ev = self._screenshot_event()
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = process_rsvp(ev, u)
        approve_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.APPROVED)
        self.assertEqual(s.unmet_requirements, [])

    def test_reinstate_stores_codes(self, _notify: MagicMock) -> None:
        ev = self.make_event(min_mmr=3000)
        u = self.make_user()
        s = EventSignup.objects.create(event=ev, user=u, status=SignupStatus.CANCELLED)
        reinstate_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(s.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])

    def test_reinstate_eligible_auto_approve_is_approved(
        self, _notify: MagicMock
    ) -> None:
        ev = self.make_event()
        s = EventSignup.objects.create(
            event=ev, user=self.make_user(), status=SignupStatus.CANCELLED
        )
        reinstate_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.APPROVED)
        self.assertEqual(s.unmet_requirements, [])

    def test_reinstate_auto_confirm_joins_roster(self, _notify: MagicMock) -> None:
        tournament = Tournament.objects.create(
            name="Reinstate Roster", date_played=tz.now(), state="future"
        )
        ev = self.make_event(auto_confirm=True, tournament=tournament)
        u = self.make_user()
        s = EventSignup.objects.create(event=ev, user=u, status=SignupStatus.CANCELLED)
        reinstate_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.CONFIRMED)
        self.assertTrue(tournament.users.filter(pk=u.pk).exists())

    def test_reinstate_manual_approval_stays_rsvp_with_codes(
        self, _notify: MagicMock
    ) -> None:
        ev = self._screenshot_event()
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = EventSignup.objects.create(event=ev, user=u, status=SignupStatus.CANCELLED)
        reinstate_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.RSVP)
        self.assertEqual(s.unmet_requirements, [Unmet.RANK_SCREENSHOT_MISSING.value])

    def test_roll_call_reinstate_clears_codes(self, _notify: MagicMock) -> None:
        ev = self.make_event(state=EventState.ROLL_CALL, min_mmr=3000)
        s = EventSignup.objects.create(
            event=ev,
            user=self.make_user(),
            status=SignupStatus.REJECTED,
            unmet_requirements=[Unmet.DOTA_RANK_UNDECLARED.value],
        )
        reinstate_signup(s)
        s.refresh_from_db()
        self.assertEqual(s.status, SignupStatus.APPROVED)
        self.assertEqual(s.unmet_requirements, [])

    def test_approve_with_mmr_override_refreshes_other_signups(
        self, _notify: MagicMock
    ) -> None:
        u = self.make_user()
        first = process_rsvp(self.make_event(require_mmr_verified=True), u)
        other = process_rsvp(self.make_event(require_mmr_verified=True), u)
        other.refresh_from_db()
        self.assertEqual(other.unmet_requirements, [Unmet.MMR_UNVERIFIED.value])
        approve_signup(first, mmr_override=5000)
        other.refresh_from_db()
        self.assertEqual(other.unmet_requirements, [])

    def test_admin_mmr_edit_refreshes_codes(self, _notify: MagicMock) -> None:
        u = self.make_user()
        s = process_rsvp(self.make_event(require_mmr_verified=True), u)
        api = APIClient()
        api.force_authenticate(self.admin)
        resp = api.patch(
            f"/api/organizations/{self.org.pk}/users/{self._org_user(u).pk}/",
            {"game_mmrs": {"1": 5000}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [])

    def test_deleting_dota_profile_restores_undeclared(
        self, _notify: MagicMock
    ) -> None:
        ev = self.make_event(auto_approve=False, min_mmr=3000)
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        s = process_rsvp(ev, u)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [])
        api = APIClient()
        api.force_authenticate(self.admin)
        resp = api.delete(
            f"/api/organizations/{self.org.pk}/users/{u.pk}/dota-profile/delete/"
        )
        self.assertEqual(resp.status_code, 204, resp.content)
        s.refresh_from_db()
        self.assertEqual(s.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])

    def test_promoted_profileless_user_pending_with_reasons(
        self, _notify: MagicMock
    ) -> None:
        ev = self.make_event(min_mmr=3000, max_players=1)
        seated = EventSignup.objects.create(
            event=ev, user=self.make_user(), status=SignupStatus.APPROVED
        )
        row = EventSignup.objects.create(
            event=ev,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        cancel_signup(seated)
        row.refresh_from_db()
        self.assertEqual(row.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(row.unmet_requirements, [Unmet.DOTA_RANK_UNDECLARED.value])


@patch("events.services.notify_signup_changed")
class UnmetRequirementsVisibilityTests(EventTestCase):
    def test_serializer_hides_codes_from_other_members(
        self, _notify: MagicMock
    ) -> None:
        ev = self.make_event(min_mmr=3000)
        owner = self.make_user()
        process_rsvp(ev, owner)
        other = self.make_user()
        api = APIClient()
        expected = {
            other: [],
            owner: [Unmet.DOTA_RANK_UNDECLARED.value],
            self.admin: [Unmet.DOTA_RANK_UNDECLARED.value],
        }
        for viewer, codes in expected.items():
            with self.subTest(viewer=viewer.username):
                api.force_authenticate(viewer)
                resp = api.get(f"/api/events/signups/?event={ev.pk}")
                self.assertEqual(resp.status_code, 200, resp.content)
                body = resp.json()
                rows = body["results"] if isinstance(body, dict) else body
                (row,) = [r for r in rows if r["user"] == owner.pk]
                self.assertEqual(row["unmet_requirements"], codes)

    def test_serializer_without_request_hides_codes(self, _notify: MagicMock) -> None:
        ev = self.make_event(min_mmr=3000)
        s = process_rsvp(ev, self.make_user())
        self.assertEqual(EventSignupSerializer(s).data["unmet_requirements"], [])
