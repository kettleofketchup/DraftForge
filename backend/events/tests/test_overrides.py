import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from events.overrides import (
    OverrideReasonRequired,
    OverrideRequired,
    Violation,
    check_overrides,
)
from org.settings_constants import ALL_CODES, StaffOverridePolicy

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _standin_cap() -> Violation:
    return Violation("team_standin_cap", "override-warning", "Stand-in cap 2", "team")


def _min_mmr() -> Violation:
    return Violation("below_min_mmr", "staff-override", "Below min MMR", "eligibility")


class CheckOverridesTest(SimpleTestCase):
    def test_team_code_raises_under_every_policy(self) -> None:
        settings_values: list[SimpleNamespace | None] = [
            SimpleNamespace(staff_override_policy=value)
            for value in StaffOverridePolicy.values
        ]
        settings_values.append(None)
        for org_settings in settings_values:
            with self.subTest(org_settings=org_settings):
                with self.assertRaises(OverrideRequired) as ctx:
                    check_overrides(
                        [_standin_cap()],
                        org_settings=org_settings,
                        acknowledged=[],
                        reason="",
                    )
                self.assertEqual(ctx.exception.violations[0].code, "team_standin_cap")
                self.assertIs(ctx.exception.blocked, False)

    def test_acknowledged_with_reason_returns_codes(self) -> None:
        codes = check_overrides(
            [_standin_cap()],
            org_settings=None,
            acknowledged=["team_standin_cap"],
            reason="Captain asked",
        )
        self.assertEqual(codes, ["team_standin_cap"])

    def test_acknowledged_without_reason_raises(self) -> None:
        for reason in ("  ", "", None):
            with self.subTest(reason=reason):
                with self.assertRaises(OverrideReasonRequired):
                    check_overrides(
                        [_standin_cap()],
                        org_settings=None,
                        acknowledged=["team_standin_cap"],
                        reason=reason,
                    )

    def test_unraised_acknowledgement_ignored(self) -> None:
        self.assertEqual(
            check_overrides([], org_settings=None, acknowledged=["x"], reason=""),
            [],
        )

    def test_partial_acknowledgement_raises_with_unacknowledged_only(self) -> None:
        with self.assertRaises(OverrideRequired) as ctx:
            check_overrides(
                [_standin_cap(), _min_mmr()],
                org_settings=None,
                acknowledged=["team_standin_cap"],
                reason="Captain asked",
            )
        self.assertEqual([v.code for v in ctx.exception.violations], ["below_min_mmr"])

    def test_all_codes_code_raises_value_error(self) -> None:
        seating = Violation(ALL_CODES[0], "override-warning", "Seating", "seating")
        with self.assertRaisesRegex(ValueError, "#585"):
            check_overrides([seating], org_settings=None, acknowledged=[], reason="r")

    def test_violation_as_dict(self) -> None:
        self.assertEqual(
            _standin_cap().as_dict(),
            {
                "code": "team_standin_cap",
                "rule": "override-warning",
                "message": "Stand-in cap 2",
                "category": "team",
            },
        )

    def test_module_loads_no_models(self) -> None:
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import events.overrides\n"
            "apps = {'app', 'events', 'org', 'league'}\n"
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
