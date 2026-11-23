#!/usr/bin/env python3
"""Tests for scripts/check-runs-on.sh against fixture workflow directories.

Stdlib only (the `runs-on-guard` CI job runs it on the bare runner, which has bash
and mikefarah yq):
    python3 -I scripts/test_check_runs_on.py
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "check-runs-on.sh"
REAL_WORKFLOWS = SCRIPTS.parent / ".github" / "workflows"

CLAUSES = [
    "vars.SELF_HOSTED_RUNNERS == 'true'",
    "github.event_name == 'pull_request'",
    "github.event.pull_request.head.repo.full_name == github.repository",
    "contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), "
    "format(',{0},', github.event.pull_request.user.login))",
    "contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), "
    "format(',{0},', github.triggering_actor))",
]
GUARD = "\n      && ".join(CLAUSES)

RUNS_ON = (
    "    runs-on: >-\n"
    "      ${{ (" + GUARD + ")\n"
    "      && 'draftforge-home' || 'ubuntu-latest' }}\n"
)
HOME_PREPARE = (
    "  HOME_PREPARE: >-\n    ${{ " + GUARD.replace("\n      ", "\n    ") + " }}\n"
)

PLAYWRIGHT = (
    """\
name: Playwright Tests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main, 'fix/**']
env:
"""
    + HOME_PREPARE
    + """\
jobs:
  prepare:
    name: Prepare images and test DB
"""
    + RUNS_ON
    + """\
    timeout-minutes: 30
    steps:
      - if: runner.environment == 'self-hosted'
        run: echo home
  test:
    needs: prepare
    if: ${{ !cancelled() }}
    runs-on: ubuntu-latest
    steps:
      - run: echo test
"""
)

OTHER = """\
name: Other
on:
  pull_request:
    branches: [main]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo lint
  local-call:
    uses: ./.github/workflows/other.yml
"""


def run_check(workflows_dir):
    return subprocess.run(
        ["bash", str(SCRIPT), str(workflows_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


class CheckRunsOnTest(unittest.TestCase):
    def check(self, playwright=PLAYWRIGHT, other=OTHER):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "playwright.yml").write_text(playwright)
            (root / "other.yml").write_text(other)
            return run_check(root)

    def assert_fails(self, result, needle):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(needle, result.stdout)

    def test_fixture_passes(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_real_workflows_pass(self):
        result = run_check(REAL_WORKFLOWS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_label_on_another_job_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace(
                "  test:\n    needs: prepare\n    if: ${{ !cancelled() }}\n    runs-on: ubuntu-latest",
                "  test:\n    needs: prepare\n    if: ${{ !cancelled() }}\n    runs-on: draftforge-home",
            )
        )
        self.assert_fails(
            result, "playwright.yml: draftforge-home at jobs test runs-on"
        )

    def test_label_in_another_workflow_fails(self):
        result = self.check(other=OTHER.replace("ubuntu-latest", "draftforge-home"))
        self.assert_fails(result, "other.yml: draftforge-home at jobs lint runs-on")

    def test_label_in_runs_on_list_form_fails(self):
        result = self.check(
            other=OTHER.replace("ubuntu-latest", "[self-hosted, draftforge-home]")
        )
        self.assert_fails(result, "other.yml: job lint runs-on 'self-hosted'")

    def test_label_outside_runs_on_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace("run: echo home", "run: echo draftforge-home")
        )
        self.assert_fails(result, "draftforge-home at jobs prepare steps 0 run")

    def test_self_hosted_literal_fails(self):
        result = self.check(other=OTHER.replace("ubuntu-latest", "self-hosted"))
        self.assert_fails(result, "job lint runs-on 'self-hosted'")

    def test_runs_on_from_a_variable_fails(self):
        # The pattern #787 shipped with: any value of the variable, any runner.
        expr = "${{ fromJSON(vars.PREPARE_RUNNER || '\"ubuntu-latest\"') }}"
        result = self.check(other=OTHER.replace("ubuntu-latest", expr))
        self.assert_fails(result, "job lint runs-on '${{ fromJSON(vars.PREPARE_RUNNER")

    def test_prepare_runs_on_from_a_variable_fails(self):
        expr = (
            "    runs-on: ${{ fromJSON(vars.PREPARE_RUNNER || '\"ubuntu-latest\"') }}\n"
        )
        result = self.check(playwright=PLAYWRIGHT.replace(RUNS_ON, expr))
        self.assert_fails(result, "job prepare runs-on is not the guarded expression")

    def test_matrix_runs_on_fails(self):
        result = self.check(other=OTHER.replace("ubuntu-latest", "${{ matrix.os }}"))
        self.assert_fails(result, "job lint runs-on '${{ matrix.os }}'")

    def test_runner_group_fails(self):
        result = self.check(
            other=OTHER.replace(
                "runs-on: ubuntu-latest",
                "runs-on:\n      group: home\n      labels: [x]",
            )
        )
        self.assert_fails(result, "job lint runs-on is a runner group")

    def test_hosted_label_list_passes(self):
        result = self.check(
            other=OTHER.replace("ubuntu-latest", "[ubuntu-24.04, ubuntu-latest]")
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_remote_reusable_workflow_fails(self):
        result = self.check(
            other=OTHER.replace(
                "./.github/workflows/other.yml",
                "someone/else/.github/workflows/x.yml@v1",
            )
        )
        self.assert_fails(result, "job local-call calls reusable workflow")

    def test_prepare_without_timeout_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace("    timeout-minutes: 30\n", "")
        )
        self.assert_fails(result, "timeout-minutes")

    def test_prepare_with_a_dropped_clause_fails(self):
        clause = "      && github.event.pull_request.head.repo.full_name == github.repository\n"
        self.assertIn(clause, RUNS_ON)
        weaker = RUNS_ON.replace(clause, "")
        result = self.check(playwright=PLAYWRIGHT.replace(RUNS_ON, weaker))
        self.assert_fails(result, "job prepare runs-on is not the guarded expression")

    def test_prepare_with_an_or_escape_fails(self):
        # Containing every clause is not enough: `|| true` makes the guard always hold.
        looser = RUNS_ON.replace(
            ")\n      && 'draftforge", " || true)\n      && 'draftforge"
        )
        self.assertNotEqual(looser, RUNS_ON)
        result = self.check(playwright=PLAYWRIGHT.replace(RUNS_ON, looser))
        self.assert_fails(result, "job prepare runs-on is not the guarded expression")

    def test_prepare_with_swapped_labels_fails(self):
        swapped = RUNS_ON.replace(
            "'draftforge-home' || 'ubuntu-latest'",
            "'ubuntu-latest' || 'draftforge-home'",
        )
        result = self.check(playwright=PLAYWRIGHT.replace(RUNS_ON, swapped))
        self.assert_fails(result, "job prepare runs-on is not the guarded expression")

    def test_prepare_runs_on_reflowed_passes(self):
        one_line = "    runs-on: " + " ".join(RUNS_ON.split()[2:]) + "\n"
        self.assertNotEqual(one_line, RUNS_ON)
        result = self.check(playwright=PLAYWRIGHT.replace(RUNS_ON, one_line))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_home_prepare_drift_fails(self):
        clause = "    && github.event.pull_request.head.repo.full_name == github.repository\n"
        self.assertIn(clause, HOME_PREPARE)
        result = self.check(
            playwright=PLAYWRIGHT.replace(
                HOME_PREPARE, HOME_PREPARE.replace(clause, "")
            )
        )
        self.assert_fails(result, "env.HOME_PREPARE is not the runs-on guard")

    def test_home_prepare_missing_fails(self):
        result = self.check(playwright=PLAYWRIGHT.replace("env:\n" + HOME_PREPARE, ""))
        self.assert_fails(result, "env.HOME_PREPARE is not the runs-on guard")

    def test_test_jobs_may_need_prepare(self):
        # #787: test jobs wait for prepare (needs + !cancelled()); that is allowed now.
        self.assertIn("needs: prepare", PLAYWRIGHT)
        self.assertEqual(self.check().returncode, 0)

    def test_pull_request_target_trigger_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace("on:\n", "on:\n  pull_request_target:\n", 1)
        )
        self.assert_fails(result, "pull_request_target")

    def test_workflow_run_trigger_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace(
                "on:\n", "on:\n  workflow_run:\n    workflows: [Other]\n", 1
            )
        )
        self.assert_fails(result, "workflow_run")

    def test_pull_request_target_workflow_cannot_reach_self_hosted(self):
        target = OTHER.replace("  pull_request:\n", "  pull_request_target:\n").replace(
            "ubuntu-latest", "self-hosted"
        )
        result = self.check(other=target)
        self.assert_fails(result, "job lint runs-on 'self-hosted'")


if __name__ == "__main__":
    unittest.main()
