from itertools import product

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings

from app.models import CustomUser, GameType
from events.discord.providers.dota import _check_dota_profile_complete
from events.eligibility import (
    REQUIREMENT_CHECKS,
    UNMET_LABELS,
    Unmet,
    has_steam_id,
    steam_friend_id_from_profiles,
    unmet_requirements,
    validate_friend_id,
)
from events.models import Event
from events.schemas import DotaModalConfig, SignupInputPatch, dota_require_screenshot
from events.services import apply_signup_input
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile

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
            patch=SignupInputPatch(unverified_friend_id="123456"),
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

    def test_has_steam_id_rejects_friend_id_owned_by_other_user(self) -> None:
        u = self.make_user()
        other = self.make_user()
        other.steam_account_id = 555555
        other.save()
        ou = self._org_user(u)
        PlayerDotaProfile.objects.create(org_user=ou, unverified_friend_id="555555")
        ou = self._org_user(u)
        self.assertFalse(has_steam_id(u, ou))

    def test_has_steam_id_accepts_own_unowned_friend_id(self) -> None:
        u = self.make_user()
        ou = self._org_user(u)
        PlayerDotaProfile.objects.create(org_user=ou, unverified_friend_id="777777")
        ou = self._org_user(u)
        self.assertTrue(has_steam_id(u, ou))

    def test_has_steam_id_rejects_non_numeric_friend_id(self) -> None:
        u = self.make_user()
        ou = self._org_user(u)
        PlayerDotaProfile.objects.create(org_user=ou, unverified_friend_id="abc")
        ou = self._org_user(u)
        self.assertFalse(has_steam_id(u, ou))

    def test_has_steam_id_account_id_range(self) -> None:
        cases = {
            "0": False,
            "99999999999999999999": False,
            str(2**32): False,
            str(2**32 - 1): True,
            str(2**31): True,
        }
        for fid, expected in cases.items():
            with self.subTest(fid=fid):
                u = self.make_user()
                PlayerDotaProfile.objects.create(
                    org_user=self._org_user(u), unverified_friend_id=fid
                )
                self.assertEqual(has_steam_id(u, self._org_user(u)), expected)

    def test_blank_or_non_numeric_dota_id_falls_back_to_deadlock(self) -> None:
        for dota_value in ("abc", "   "):
            with self.subTest(dota_value=dota_value):
                u = self.make_user()
                ou = self._org_user(u)
                PlayerDotaProfile.objects.create(
                    org_user=ou, unverified_friend_id=dota_value
                )
                PlayerDeadlockProfile.objects.create(
                    org_user=ou, unverified_friend_id="246810"
                )
                ou = self._org_user(u)
                self.assertEqual(steam_friend_id_from_profiles(ou), "246810")
                self.assertTrue(has_steam_id(u, ou))

    def test_require_steam_id_met_by_profile_friend_id(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        PlayerDotaProfile.objects.create(
            org_user=self._org_user(u), unverified_friend_id="888888"
        )
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
    def _org_user(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=self.org)

    def test_leading_zero_and_whitespace_collide_by_value(self) -> None:
        u = self.make_user()
        other = self.make_user()
        other.steam_account_id = 123
        other.save()
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id(" 0123 ", self._org_user(u))
        self.assertEqual(cm.exception.code, "duplicate_friend_id")

    def test_returns_stripped_value(self) -> None:
        u = self.make_user()
        self.assertEqual(validate_friend_id(" 424242 ", self._org_user(u)), "424242")

    def test_own_steam_account_id_is_not_a_collision(self) -> None:
        u = self.make_user()
        u.steam_account_id = 31337
        u.save()
        self.assertEqual(validate_friend_id("31337", self._org_user(u)), "31337")

    def test_length_boundaries(self) -> None:
        ou = self._org_user(self.make_user())
        for fid in ("1234567890", "12345678901", "9" * 20):
            with self.subTest(fid=fid):
                self.assertEqual(validate_friend_id(fid, ou), fid)
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("9" * 21, ou)
        self.assertEqual(cm.exception.code, "invalid_friend_id")

    def test_non_numeric_is_invalid(self) -> None:
        ou = self._org_user(self.make_user())
        for fid in ("abc", "12a", "١٢٣"):
            with self.subTest(fid=fid):
                with self.assertRaises(DjangoValidationError) as cm:
                    validate_friend_id(fid, ou)
                self.assertEqual(cm.exception.code, "invalid_friend_id")

    def test_out_of_range_still_checks_profiles(self) -> None:
        fid = "9" * 20
        other = self._org_user(self.make_user())
        PlayerDotaProfile.objects.create(org_user=other, unverified_friend_id=fid)
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id(fid, self._org_user(self.make_user()))
        self.assertEqual(cm.exception.code, "duplicate_friend_id")

    def test_collides_with_deadlock_profile_of_other_user(self) -> None:
        other = self._org_user(self.make_user())
        PlayerDeadlockProfile.objects.create(
            org_user=other, unverified_friend_id="565656"
        )
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("565656", self._org_user(self.make_user()))
        self.assertEqual(cm.exception.code, "duplicate_friend_id")

    def test_leading_zero_collides_with_other_profile(self) -> None:
        other = self._org_user(self.make_user())
        PlayerDotaProfile.objects.create(org_user=other, unverified_friend_id="123")
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("0123", self._org_user(self.make_user()))
        self.assertEqual(cm.exception.code, "duplicate_friend_id")

    def test_returns_canonical_form(self) -> None:
        ou = self._org_user(self.make_user())
        self.assertEqual(validate_friend_id(" 00424242 ", ou), "424242")

    @override_settings(SITE_URL="https://events.example.test")
    def test_duplicate_message_points_at_site_url(self) -> None:
        other = self._org_user(self.make_user())
        PlayerDotaProfile.objects.create(org_user=other, unverified_friend_id="454545")
        with self.assertRaises(DjangoValidationError) as cm:
            validate_friend_id("454545", self._org_user(self.make_user()))
        self.assertIn("https://events.example.test", cm.exception.messages[0])
        self.assertNotIn("dota.kettle.sh", cm.exception.messages[0])

    def test_own_profiles_are_not_a_collision(self) -> None:
        ou = self._org_user(self.make_user())
        PlayerDotaProfile.objects.create(org_user=ou, unverified_friend_id="676767")
        PlayerDeadlockProfile.objects.create(org_user=ou, unverified_friend_id="676767")
        self.assertEqual(validate_friend_id("676767", ou), "676767")
