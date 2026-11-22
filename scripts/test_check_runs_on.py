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

PREPARE_IF = """\
    if: >-
      vars.SELF_HOSTED_RUNNERS == 'true'
      && github.event_name == 'pull_request'
      && github.event.pull_request.head.repo.full_name == github.repository
      && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.event.pull_request.user.login))
      && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.triggering_actor))
"""

PLAYWRIGHT = (
    """\
name: Playwright Tests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main, 'fix/**']
jobs:
  prepare:
    name: Prepare images on the home runner
"""
    + PREPARE_IF
    + """\
    runs-on: draftforge-home
    timeout-minutes: 15
    steps:
      - run: echo prepare
  test:
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
                "  test:\n    runs-on: ubuntu-latest",
                "  test:\n    runs-on: draftforge-home",
            )
        )
        self.assert_fails(result, "playwright.yml: job test")

    def test_label_in_another_workflow_fails(self):
        result = self.check(other=OTHER.replace("ubuntu-latest", "draftforge-home"))
        self.assert_fails(result, "other.yml: job lint")

    def test_label_in_runs_on_list_form_fails(self):
        result = self.check(
            other=OTHER.replace("ubuntu-latest", "[self-hosted, draftforge-home]")
        )
        self.assert_fails(result, "other.yml: job lint")

    def test_prepare_without_timeout_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace("    timeout-minutes: 15\n", "")
        )
        self.assert_fails(result, "timeout-minutes")

    def test_prepare_with_weaker_if_fails(self):
        clause = "      && github.event.pull_request.head.repo.full_name == github.repository\n"
        self.assertIn(clause, PLAYWRIGHT)
        result = self.check(playwright=PLAYWRIGHT.replace(clause, ""))
        self.assert_fails(result, "head.repo.full_name")

    def test_prepare_if_reflowed_passes(self):
        reflowed = PLAYWRIGHT.replace(
            PREPARE_IF, "    if: " + " ".join(PREPARE_IF.split()[2:]) + "\n"
        )
        self.assertNotEqual(reflowed, PLAYWRIGHT)
        result = self.check(playwright=reflowed)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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


if __name__ == "__main__":
    unittest.main()
