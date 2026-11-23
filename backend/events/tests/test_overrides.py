import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from events import overrides
from events.overrides import (
    REASON_MAX_LENGTH,
    OverrideReasonRequired,
    OverrideRequired,
    Violation,
    check_overrides,
    parse_override_request,
    resolve_overrides,
)
from org.settings_constants import ALL_CODES, StaffOverridePolicy

BACKEND_DIR = Path(__file__).resolve().parents[2]
TICKED = "over_capacity"
UNTICKED = "gate_outside"


def _settings(policy: str, warning_codes: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        organization_id=7,
        staff_override_policy=policy,
        staff_override_warning_codes=[TICKED]
        if warning_codes is None
        else warning_codes,
    )


def _seat(code: str = TICKED) -> Violation:
    return Violation(
        code,
        "override-warning",
        "Roster A is over capacity (11/10)",
        "seating",
        params={"roster": "A", "count": 11, "capacity": 10},
    )


def _standin_cap() -> Violation:
    return Violation("team_standin_cap", "override-warning", "Stand-in cap 2", "team")


def _min_mmr() -> Violation:
    return Violation(
        "below_min_mmr",
        "staff-override",
        "MMR 2,400 is below Roster A's 3,000 gate",
        "eligibility",
        params={"mmr": 2400, "min_mmr": 3000},
    )


class PolicyMatrixTest(SimpleTestCase):
    def test_silent_passes_seating_with_null_reason(self) -> None:
        for settings in (None, _settings(StaffOverridePolicy.SILENT)):
            with self.subTest(settings=settings):
                result = resolve_overrides(
                    [_seat(), _seat(UNTICKED)],
                    org_settings=settings,
                    acknowledged=[],
                    reason="",
                )
                self.assertEqual(result.overridden, [TICKED, UNTICKED])
                self.assertEqual(result.prompted, [])
                self.assertIsNone(result.reason)

    def test_non_seating_raises_under_every_policy(self) -> None:
        options: list[SimpleNamespace | None] = [
            _settings(value) for value in StaffOverridePolicy.values
        ]
        options.append(None)
        for settings in options:
            for violation in (_standin_cap(), _min_mmr()):
                with self.subTest(settings=settings, code=violation.code):
                    with self.assertRaises(OverrideRequired) as ctx:
                        check_overrides(
                            [violation],
                            org_settings=settings,
                            acknowledged=[],
                            reason="",
                        )
                    self.assertEqual(ctx.exception.violations[0].code, violation.code)
                    self.assertIs(ctx.exception.violations[0].blocking, False)
                    self.assertIs(ctx.exception.blocked, False)

    def test_non_seating_never_filtered_by_warning_set(self) -> None:
        settings = _settings(StaffOverridePolicy.CONFIRM, warning_codes=[])
        with self.assertRaises(OverrideRequired):
            check_overrides(
                [_min_mmr()], org_settings=settings, acknowledged=[], reason=""
            )

    def test_confirm_ticked_raises_until_acknowledged(self) -> None:
        settings = _settings(StaffOverridePolicy.CONFIRM)
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_seat()], org_settings=settings, acknowledged=[], reason="r"
            )
        self.assertFalse(ctx.exception.blocked)
        self.assertEqual([v.code for v in ctx.exception.violations], [TICKED])

        result = resolve_overrides(
            [_seat()], org_settings=settings, acknowledged=[TICKED], reason=" ok "
        )
        self.assertEqual(result.overridden, [TICKED])
        self.assertEqual(result.prompted, [TICKED])
        self.assertEqual(result.reason, "ok")

    def test_confirm_unticked_never_prompts(self) -> None:
        settings = _settings(StaffOverridePolicy.CONFIRM)
        result = resolve_overrides(
            [_seat(UNTICKED)], org_settings=settings, acknowledged=[], reason=None
        )
        self.assertEqual(result.overridden, [UNTICKED])
        self.assertIsNone(result.reason)

    def test_confirm_mixed_unticked_and_ticked(self) -> None:
        settings = _settings(StaffOverridePolicy.CONFIRM)
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_seat(UNTICKED), _seat()],
                org_settings=settings,
                acknowledged=[],
                reason="",
            )
        self.assertEqual([v.code for v in ctx.exception.violations], [TICKED])
        result = resolve_overrides(
            [_seat(UNTICKED), _seat()],
            org_settings=settings,
            acknowledged=[TICKED],
            reason="captain asked",
        )
        self.assertEqual(result.overridden, [UNTICKED, TICKED])
        self.assertEqual(result.prompted, [TICKED])

    def test_block_ticked_is_blocked_even_if_acknowledged(self) -> None:
        settings = _settings(StaffOverridePolicy.BLOCK)
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_seat()], org_settings=settings, acknowledged=[TICKED], reason="r"
            )
        self.assertTrue(ctx.exception.blocked)
        self.assertTrue(ctx.exception.violations[0].blocking)

    def test_block_unticked_passes(self) -> None:
        settings = _settings(StaffOverridePolicy.BLOCK)
        self.assertEqual(
            check_overrides(
                [_seat(UNTICKED)], org_settings=settings, acknowledged=[], reason=""
            ),
            [UNTICKED],
        )

    def test_block_eligibility_uses_confirm_flow(self) -> None:
        settings = _settings(StaffOverridePolicy.BLOCK)
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_min_mmr()], org_settings=settings, acknowledged=[], reason=""
            )
        self.assertFalse(ctx.exception.blocked)
        self.assertEqual(
            check_overrides(
                [_min_mmr()],
                org_settings=settings,
                acknowledged=["below_min_mmr"],
                reason="known player",
            ),
            ["below_min_mmr"],
        )

    def test_blocked_and_confirmable_lists_both(self) -> None:
        settings = _settings(StaffOverridePolicy.BLOCK)
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_min_mmr(), _seat(), _seat(UNTICKED)],
                org_settings=settings,
                acknowledged=["below_min_mmr"],
                reason="r",
            )
        self.assertTrue(ctx.exception.blocked)
        self.assertEqual(
            [(v.code, v.blocking) for v in ctx.exception.violations],
            [("below_min_mmr", False), (TICKED, True)],
        )

    def test_blocked_notifies_seam(self) -> None:
        settings = _settings(StaffOverridePolicy.BLOCK)
        calls: list[tuple[list[str], Any]] = []
        original = overrides.notify_override_blocked

        def spy(violations: list[Violation], *, org_settings: Any) -> None:
            calls.append(([v.code for v in violations], org_settings))
            original(violations, org_settings=org_settings)

        overrides.notify_override_blocked = spy  # type: ignore[assignment]
        try:
            with self.assertRaises(OverrideRequired):
                check_overrides(
                    [_seat()], org_settings=settings, acknowledged=[], reason=""
                )
        finally:
            overrides.notify_override_blocked = original  # type: ignore[assignment]
        self.assertEqual(calls, [([TICKED], settings)])

    def test_caller_blocking_flag_is_ignored_for_non_seating(self) -> None:
        violation = Violation(
            "below_min_mmr", "staff-override", "m", "eligibility", True
        )
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides([violation], org_settings=None, acknowledged=[], reason="")
        self.assertFalse(ctx.exception.blocked)


class AcknowledgementTest(SimpleTestCase):
    def test_acknowledged_with_reason_returns_codes(self) -> None:
        codes = check_overrides(
            [_standin_cap()],
            org_settings=None,
            acknowledged=["team_standin_cap"],
            reason="Captain asked",
        )
        self.assertEqual(codes, ["team_standin_cap"])

    def test_invalid_reason_raises(self) -> None:
        for reason in ("  ", "", None, "x" * (REASON_MAX_LENGTH + 1)):
            with self.subTest(reason=reason):
                with self.assertRaises(OverrideReasonRequired):
                    check_overrides(
                        [_standin_cap()],
                        org_settings=None,
                        acknowledged=["team_standin_cap"],
                        reason=reason,
                    )

    def test_reason_at_limit_after_trim_passes(self) -> None:
        result = resolve_overrides(
            [_standin_cap()],
            org_settings=None,
            acknowledged=["team_standin_cap"],
            reason=f"  {'x' * REASON_MAX_LENGTH}  ",
        )
        self.assertEqual(result.reason, "x" * REASON_MAX_LENGTH)

    def test_unraised_acknowledgement_ignored(self) -> None:
        self.assertEqual(
            check_overrides([], org_settings=None, acknowledged=["x"], reason=""),
            [],
        )

    def test_new_violation_prompts_again(self) -> None:
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_standin_cap(), _min_mmr()],
                org_settings=None,
                acknowledged=["team_standin_cap"],
                reason="Captain asked",
            )
        self.assertEqual([v.code for v in ctx.exception.violations], ["below_min_mmr"])


class ViolationTest(SimpleTestCase):
    def test_as_dict(self) -> None:
        self.assertEqual(
            _standin_cap().as_dict(),
            {
                "code": "team_standin_cap",
                "rule": "override-warning",
                "message": "Stand-in cap 2",
                "category": "team",
                "blocking": False,
                "params": {},
            },
        )

    def test_hashable_with_params(self) -> None:
        self.assertEqual(len({_seat(), _seat()}), 1)

    def test_override_required_blocked_derived(self) -> None:
        blocking = Violation(TICKED, "staff-override", "m", "seating", blocking=True)
        self.assertTrue(OverrideRequired([blocking]).blocked)
        self.assertFalse(OverrideRequired([_min_mmr()]).blocked)


class ParseOverrideRequestTest(SimpleTestCase):
    def test_defaults(self) -> None:
        parsed = parse_override_request({})
        self.assertEqual(parsed.acknowledged_codes, [])
        self.assertEqual(parsed.reason, "")

    def test_values(self) -> None:
        parsed = parse_override_request(
            {"acknowledged_codes": [TICKED], "reason": " why "}
        )
        self.assertEqual(parsed.acknowledged_codes, [TICKED])
        self.assertEqual(parsed.reason, " why ")

    def test_null_reason(self) -> None:
        self.assertEqual(parse_override_request({"reason": None}).reason, "")

    def test_malformed_codes_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            parse_override_request({"acknowledged_codes": "over_capacity"})


class ExampleOverrideView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    org_settings: SimpleNamespace | None = None
    violations: list[Violation] = []

    def post(self, request: Request) -> Response:
        parsed = parse_override_request(request.data)
        result = resolve_overrides(
            self.violations,
            org_settings=self.org_settings,
            acknowledged=parsed.acknowledged_codes,
            reason=parsed.reason,
        )
        return Response({"overridden": result.overridden, "reason": result.reason})


class ExceptionHandlerTest(SimpleTestCase):
    def post(
        self,
        body: dict[str, object],
        violations: list[Violation],
        settings: SimpleNamespace | None = None,
    ) -> Response:
        view = ExampleOverrideView.as_view(org_settings=settings, violations=violations)
        request = APIRequestFactory().post("/example/", body, format="json")
        response = view(request)
        response.render()
        return response

    def test_409_shape(self) -> None:
        response = self.post({}, [_min_mmr()])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {
                "code": "override_required",
                "blocked": False,
                "violations": [
                    {
                        "code": "below_min_mmr",
                        "rule": "staff-override",
                        "category": "eligibility",
                        "message": "MMR 2,400 is below Roster A's 3,000 gate",
                        "blocking": False,
                        "params": {"mmr": 2400, "min_mmr": 3000},
                    }
                ],
            },
        )

    def test_409_blocked(self) -> None:
        response = self.post(
            {"acknowledged_codes": [TICKED, "below_min_mmr"], "reason": "r"},
            [_seat(), _min_mmr()],
            _settings(StaffOverridePolicy.BLOCK),
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data["blocked"])
        self.assertEqual(
            [(v["code"], v["blocking"]) for v in response.data["violations"]],
            [(TICKED, True), ("below_min_mmr", False)],
        )

    def test_400_reason_required(self) -> None:
        response = self.post({"acknowledged_codes": ["below_min_mmr"]}, [_min_mmr()])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"code": "override_reason_required"})

    def test_200_after_acknowledgement(self) -> None:
        response = self.post(
            {"acknowledged_codes": ["below_min_mmr", "stale"], "reason": " known "},
            [_min_mmr()],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"overridden": ["below_min_mmr"], "reason": "known"}
        )

    def test_200_silent_null_reason(self) -> None:
        response = self.post({}, [_seat()], _settings(StaffOverridePolicy.SILENT))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"overridden": [TICKED], "reason": None})


class ModuleImportTest(SimpleTestCase):
    def test_module_loads_no_models(self) -> None:
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import events.overrides\n"
            "apps = {'app', 'events', 'org', 'league', 'tournament'}\n"
            "print(sorted(m for m in sys.modules\n"
            "    if m.split('.')[0] in apps and '.models' in m))"
        )
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings"}
        result = subprocess.run(
            [sys.executable, "-c", code, str(BACKEND_DIR)],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")

    def test_all_codes_are_seating(self) -> None:
        self.assertIn(TICKED, ALL_CODES)
        self.assertIn(UNTICKED, ALL_CODES)
