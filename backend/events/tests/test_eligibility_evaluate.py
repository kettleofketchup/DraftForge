from collections.abc import Callable
from itertools import product
from unittest.mock import patch

from django.conf import settings
from structlog.testing import capture_logs

from app.models import CustomUser, GameType
from events.constants import Commitment
from events.eligibility import (
    CHECKS,
    EvalContext,
    FixKind,
    GatedMetric,
    Reason,
    ReasonCode,
    Rule,
    Severity,
    evaluate_signup,
    gated_metrics,
    has_registered_steam_id,
    is_skill_gated,
    unmet_codes,
)
from events.models import Event
from events.schemas import DotaModalConfig, dota_require_screenshot
from events.services import check_requirements
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile

PROFILE_URL = f"{settings.SITE_URL}/profile"


def _legacy_has_steam_id(user: CustomUser, org_user: OrgUser | None) -> bool:
    if user.steamid:
        return True
    fid = ""
    for attr in ("dota_profile", "deadlock_profile"):
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        value = (value or "").strip()
        if value.isascii() and value.isdigit():
            fid = value
            break
    if not fid:
        return False
    account_id = int(fid)
    if account_id not in range(1, 2**32):
        return False
    if account_id > 2**31 - 1:
        return True
    return (
        not CustomUser.objects.filter(steam_account_id=account_id)
        .exclude(pk=user.pk)
        .exists()
    )


def _legacy_rank_codes(event: Event, profile: PlayerDotaProfile) -> list[str]:
    cfg = DotaModalConfig.from_event(event)
    status = profile.rank_status
    codes: list[str] = []
    if not cfg.allows_rank_status(status):
        codes.append("rank_type_disallowed")
    if dota_require_screenshot(status, cfg):
        if status == "active" and not profile.rank_screenshot:
            codes.append("rank_screenshot_missing")
        if status == "never" and not profile.battlecup_screenshot:
            codes.append("battlecup_screenshot_missing")
    if cfg.min_mmr and status == "active":
        if not profile.mmr or profile.mmr < cfg.min_mmr:
            codes.append("below_min_mmr")
    return codes


def _legacy_unmet(event: Event, user: CustomUser) -> list[str]:
    """events.eligibility.unmet_requirements as of 0.15.0, frozen for parity."""
    org_user = (
        OrgUser.objects.filter(user=user, organization_id=event.organization_id).first()
        if event.organization_id is not None
        else None
    )
    dota = GameType(event.game_type) == GameType.DOTA2
    steam_ok = (
        _legacy_has_steam_id(user, org_user)
        if event.require_steam_id or event.require_profile_complete
        else True
    )
    codes: list[str] = []
    if event.require_steam_id and not steam_ok:
        codes.append("steam_id_missing")
    mmr_ok = bool(org_user and org_user.has_active_dota_mmr) if dota else True
    if event.require_mmr_verified and not mmr_ok:
        codes.append("mmr_unverified")
    if event.require_profile_complete and not (
        user.nickname and steam_ok and user.discordId
    ):
        codes.append("profile_incomplete")
    if dota:
        profile = getattr(org_user, "dota_profile", None)
        if profile is None or not profile.is_rank_declared:
            probes = (
                PlayerDotaProfile(rank_status=s)
                for s in PlayerDotaProfile.RANK_STATUSES
            )
            if any(_legacy_rank_codes(event, p) for p in probes):
                codes.append("dota_rank_undeclared")
        else:
            codes.extend(_legacy_rank_codes(event, profile))
    return list(dict.fromkeys(codes))


class EvaluatorTestCase(EventTestCase):
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

    def _only_reason(self, event: Event, user: CustomUser) -> Reason:
        result = evaluate_signup(event, user)
        self.assertEqual(len(result.reasons), 1, result.codes)
        reason = result.reasons[0]
        self.assertEqual(reason.severity, Severity.NEEDS_APPROVAL)
        self.assertTrue(reason.message)
        return reason


class PortedRuleTests(EvaluatorTestCase):
    def test_steam_id_missing(self) -> None:
        reason = self._only_reason(
            self.make_event(require_steam_id=True), self.make_user()
        )
        self.assertEqual(reason.code, ReasonCode.STEAM_ID_MISSING)
        self.assertEqual(reason.rule, Rule.REQUIRE_STEAM_ID)
        assert reason.fix is not None
        self.assertEqual(reason.fix.kind, FixKind.UPDATE_PROFILE)
        self.assertEqual(reason.fix.url, PROFILE_URL)

    def test_mmr_unverified(self) -> None:
        reason = self._only_reason(
            self.make_event(require_mmr_verified=True), self.make_user()
        )
        self.assertEqual(reason.code, ReasonCode.MMR_UNVERIFIED)
        self.assertEqual(reason.rule, Rule.REQUIRE_MMR_VERIFIED)
        self.assertIsNone(reason.fix)

    def test_profile_incomplete(self) -> None:
        reason = self._only_reason(
            self.make_event(require_profile_complete=True),
            self.make_user(steamid=76561198000123456),
        )
        self.assertEqual(reason.code, ReasonCode.PROFILE_INCOMPLETE)
        self.assertEqual(reason.rule, Rule.REQUIRE_PROFILE_COMPLETE)
        assert reason.fix is not None
        self.assertEqual(reason.fix.kind, FixKind.UPDATE_PROFILE)

    def test_rank_undeclared(self) -> None:
        reason = self._only_reason(self.make_event(min_mmr=3000), self.make_user())
        self.assertEqual(reason.code, ReasonCode.DOTA_RANK_UNDECLARED)
        self.assertEqual(reason.rule, Rule.DOTA_RANK_DECLARED)

    def test_rank_type_not_allowed(self) -> None:
        u = self.make_user()
        self._declared(u, "previous")
        reason = self._only_reason(self.make_event(allow_previous_rank=False), u)
        self.assertEqual(reason.code, ReasonCode.RANK_TYPE_DISALLOWED)
        self.assertEqual(reason.rule, Rule.DOTA_RANK_TYPE)
        self.assertEqual(reason.params, {"rank_status": "previous"})

    def test_rank_screenshot_missing(self) -> None:
        u = self.make_user()
        self._declared(u, "active", mmr=4000)
        reason = self._only_reason(
            self.make_event(discord_require_rank_screenshot=True), u
        )
        self.assertEqual(reason.code, ReasonCode.RANK_SCREENSHOT_MISSING)
        self.assertEqual(reason.rule, Rule.DOTA_RANK_SCREENSHOT)

    def test_battlecup_screenshot_missing(self) -> None:
        u = self.make_user()
        self._declared(u, "never")
        reason = self._only_reason(
            self.make_event(discord_require_battlecup_screenshot=True), u
        )
        self.assertEqual(reason.code, ReasonCode.BATTLECUP_SCREENSHOT_MISSING)
        self.assertEqual(reason.rule, Rule.DOTA_BATTLECUP_SCREENSHOT)

    def test_mmr_below_min(self) -> None:
        u = self.make_user()
        self._declared(u, "active", mmr=2000)
        reason = self._only_reason(self.make_event(min_mmr=3000), u)
        self.assertEqual(reason.code, ReasonCode.BELOW_MIN_MMR)
        self.assertEqual(reason.rule, Rule.DOTA_MIN_MMR)
        self.assertEqual(reason.params, {"min_mmr": 3000, "mmr": 2000})

    def test_one_reason_per_failing_rule_in_order(self) -> None:
        ev = self.make_event(
            require_steam_id=True,
            require_mmr_verified=True,
            require_profile_complete=True,
            min_mmr=3000,
        )
        result = evaluate_signup(ev, self.make_user())
        self.assertEqual(
            result.codes,
            [
                ReasonCode.STEAM_ID_MISSING,
                ReasonCode.MMR_UNVERIFIED,
                ReasonCode.PROFILE_INCOMPLETE,
                ReasonCode.DOTA_RANK_UNDECLARED,
            ],
        )
        self.assertTrue(result.admissible)
        self.assertFalse(result.clean)
        self.assertEqual(result.blocking, ())
        self.assertEqual(len(result.approval), 4)

    def test_clean_result(self) -> None:
        result = evaluate_signup(self.make_event(), self.make_user())
        self.assertTrue(result.clean)
        self.assertTrue(result.admissible)
        self.assertEqual(result.as_dicts(), [])

    def test_as_dict_shape(self) -> None:
        result = evaluate_signup(
            self.make_event(require_steam_id=True), self.make_user()
        )
        self.assertEqual(
            result.as_dicts(),
            [
                {
                    "code": "steam_id_missing",
                    "severity": "needs_approval",
                    "rule": "require-steam-id",
                    "message": result.reasons[0].message,
                    "fix": {"kind": "update_profile", "url": PROFILE_URL},
                    "params": {},
                }
            ],
        )

    def test_logs_evaluation(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        with capture_logs() as logs:
            evaluate_signup(ev, u, intent="maybe")
        (entry,) = [e for e in logs if e["event"] == "eligibility_evaluated"]
        self.assertEqual(entry["system"], "events")
        self.assertEqual(entry["subsystem"], "eligibility")
        self.assertEqual(entry["codes"], ["steam_id_missing"])
        self.assertTrue(entry["admissible"])
        self.assertEqual(entry["intent"], "maybe")


class RegistryTests(EvaluatorTestCase):
    def _blocking_check(self) -> Callable[[EvalContext], list[Reason]]:
        def check(ctx: EvalContext) -> list[Reason]:
            return [
                Reason(
                    code=ReasonCode.STEAM_ID_MISSING,
                    severity=Severity.BLOCK,
                    rule="test-rule",
                    message="blocked",
                )
            ]

        return check

    def test_later_check_is_appended_and_codes_dedupe(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        with patch(
            "events.eligibility.evaluate.CHECKS", (*CHECKS, self._blocking_check())
        ):
            result = evaluate_signup(ev, u)
        self.assertEqual(result.codes, ["steam_id_missing"])
        self.assertEqual(result.reasons[0].severity, Severity.NEEDS_APPROVAL)

    def test_blocking_reason_is_not_admissible(self) -> None:
        ev = self.make_event()
        u = self.make_user()
        with patch("events.eligibility.evaluate.CHECKS", (self._blocking_check(),)):
            result = evaluate_signup(ev, u)
            self.assertTrue(check_requirements(ev, u))
        self.assertFalse(result.admissible)
        self.assertEqual(result.approval, ())

    def test_context_is_loaded_once_and_never_creates_org_user(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        OrgUser.objects.filter(user=u).delete()
        seen: list[EvalContext] = []

        def spy(ctx: EvalContext) -> list[Reason]:
            seen.append(ctx)
            return []

        with patch("events.eligibility.evaluate.CHECKS", (spy, spy)):
            evaluate_signup(
                ev,
                u,
                intent=Commitment.MAYBE,
                actor=self.admin,
                discord_role_ids=["1", "2"],
                for_staff_placement=True,
            )
        self.assertIs(seen[0], seen[1])
        ctx = seen[0]
        self.assertIsNone(ctx.org_user)
        self.assertEqual(ctx.intent, Commitment.MAYBE)
        self.assertEqual(ctx.actor, self.admin)
        self.assertEqual(ctx.discord_role_ids, frozenset({"1", "2"}))
        self.assertTrue(ctx.for_staff_placement)
        self.assertFalse(OrgUser.objects.filter(user=u).exists())


class GatingTests(EvaluatorTestCase):
    def test_gated_metrics(self) -> None:
        cases: list[tuple[dict[str, object], frozenset[GatedMetric]]] = [
            ({}, frozenset()),
            ({"min_mmr": 3000}, frozenset({GatedMetric.MMR})),
            ({"require_mmr_verified": True}, frozenset({GatedMetric.MMR})),
            ({"discord_require_rank_screenshot": True}, frozenset({GatedMetric.MMR})),
            (
                {"discord_require_battlecup_screenshot": True},
                frozenset({GatedMetric.BATTLE_CUP}),
            ),
            (
                {"game_type": GameType.DEADLOCK, "min_mmr": 3000},
                frozenset(),
            ),
        ]
        for fields, expected in cases:
            with self.subTest(**{k: str(v) for k, v in fields.items()}):
                ev = self.make_event(**fields)
                self.assertEqual(gated_metrics(ev), expected)
                self.assertEqual(is_skill_gated(ev), bool(expected))

    def test_has_registered_steam_id(self) -> None:
        self.assertTrue(
            has_registered_steam_id(self.make_user(steamid=76561198000000099), None)
        )
        u = self.make_user()
        self.assertFalse(has_registered_steam_id(u, self._org_user(u)))
        PlayerDeadlockProfile.objects.create(
            org_user=self._org_user(u), unverified_friend_id="424242"
        )
        self.assertTrue(has_registered_steam_id(u, self._org_user(u)))


class CheckRequirementsParityTests(EvaluatorTestCase):
    """check_requirements and the stored codes match the 0.15.0 function."""

    REQUIRE_FLAGS = (
        "require_steam_id",
        "require_mmr_verified",
        "require_profile_complete",
    )
    GATES: tuple[dict[str, object], ...] = (
        {},
        {"min_mmr": 3000},
        {"allow_previous_rank": False},
        {"allow_active_mmr": False, "allow_battlecup_rating": False},
        {"discord_require_rank_screenshot": True},
        {"discord_require_battlecup_screenshot": True},
    )

    def _users(self) -> dict[str, CustomUser]:
        users: dict[str, CustomUser] = {}
        users["bare"] = self.make_user()
        users["base_complete"] = self.user
        OrgUser.objects.get_or_create(user=self.user, organization=self.org)

        complete = self.make_user(steamid=76561198000004444)
        complete.nickname = "Complete"
        complete.discordId = "44444"
        complete.save()
        ou = self._org_user(complete)
        ou.has_active_dota_mmr = True
        ou.save()
        self._declared(
            complete, "active", mmr=5000, rank_screenshot="https://x.test/r.png"
        )
        users["complete_active"] = complete

        friend = self.make_user()
        PlayerDotaProfile.objects.create(
            org_user=self._org_user(friend), unverified_friend_id="606060"
        )
        users["friend_id_undeclared"] = friend

        owned = self.make_user()
        holder = self.make_user()
        holder.steam_account_id = 616161
        holder.save()
        PlayerDotaProfile.objects.create(
            org_user=self._org_user(owned), unverified_friend_id="616161"
        )
        users["friend_id_owned_elsewhere"] = owned

        low = self.make_user()
        self._declared(low, "active", mmr=1000)
        users["active_low_no_shot"] = low

        prev = self.make_user()
        self._declared(prev, "previous")
        users["previous"] = prev

        never = self.make_user()
        self._declared(never, "never", battlecup_screenshot="https://x.test/b.png")
        users["never_with_shot"] = never

        never_bare = self.make_user()
        self._declared(never_bare, "never")
        users["never_no_shot"] = never_bare

        deadlock = self.make_user()
        PlayerDeadlockProfile.objects.create(
            org_user=self._org_user(deadlock), unverified_friend_id="626262"
        )
        users["deadlock_friend_id"] = deadlock

        orgless = self.make_user()
        OrgUser.objects.filter(user=orgless).delete()
        users["no_org_user"] = orgless
        return users

    def test_parity_table(self) -> None:
        users = self._users()
        compared = 0
        for game, gate, flags in product(
            (GameType.DOTA2, GameType.DEADLOCK),
            self.GATES,
            product((False, True), repeat=len(self.REQUIRE_FLAGS)),
        ):
            ev = self.make_event(
                game_type=game, **gate, **dict(zip(self.REQUIRE_FLAGS, flags))
            )
            for label, user in users.items():
                legacy = _legacy_unmet(ev, user)
                with self.subTest(game=game, gate=gate, flags=flags, user=label):
                    self.assertEqual(check_requirements(ev, user), not legacy)
                    self.assertEqual(unmet_codes(ev, user), legacy)
                compared += 1
        self.assertEqual(compared, 2 * len(self.GATES) * 8 * len(users))

    def test_every_code_is_reachable_in_the_table(self) -> None:
        users = self._users()
        seen: set[str] = set()
        for gate, flags in product(
            self.GATES, product((False, True), repeat=len(self.REQUIRE_FLAGS))
        ):
            ev = self.make_event(**gate, **dict(zip(self.REQUIRE_FLAGS, flags)))
            for user in users.values():
                seen.update(_legacy_unmet(ev, user))
        self.assertEqual(seen, set(ReasonCode.values))
