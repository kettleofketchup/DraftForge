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

# Exactly the allowlist in check-runs-on.sh, as (workflow file, job id).
ALLOWED = [
    ("playwright.yml", "prepare"),
    ("unit-tests.yml", "typecheck"),
    ("changelog.yml", "changelog"),
    ("shellcheck.yml", "shellcheck"),
    ("shellcheck.yml", "runs-on-guard"),
    ("frontend-format.yml", "prettier"),
    ("frontend-shadcn-lint.yml", "shadcn-lint"),
    ("pr-labeler.yml", "label"),
]

PR_TRIGGER = """\
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
"""


def home_job(job):
    return (
        f"  {job}:\n"
        + RUNS_ON
        + "    timeout-minutes: 10\n"
        + "    steps:\n"
        + f"      - run: echo {job}\n"
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
    + "jobs:\n"
    + home_job("prepare")
    + """\
  test:
    needs: prepare
    if: ${{ !cancelled() }}
    runs-on: ubuntu-latest
    steps:
      - run: echo test
"""
)

ISSUE_LABELER = """\
name: Auto-label issues
on:
  issues:
    types: [opened]
jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - run: echo label
"""

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


def fixture():
    """Every allowlisted workflow with its jobs guarded, plus two hosted-only ones."""
    files = {"playwright.yml": PLAYWRIGHT}
    for name, job in ALLOWED:
        if name == "playwright.yml":
            continue
        files.setdefault(name, f"name: {name}\n{PR_TRIGGER}jobs:\n")
        files[name] += home_job(job)
    files["issue-labeler.yml"] = ISSUE_LABELER
    files["other.yml"] = OTHER
    return files


def run_check(workflows_dir):
    return subprocess.run(
        ["bash", str(SCRIPT), str(workflows_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


def replace_job_runs_on(text, job, new_runs_on):
    """Swap one guarded job's runs-on block for new_runs_on."""
    old = f"  {job}:\n" + RUNS_ON
    assert old in text, job
    return text.replace(old, f"  {job}:\n" + new_runs_on)


class CheckRunsOnTest(unittest.TestCase):
    def check(self, **overrides):
        """Run the guard on the fixture; overrides map file name to text (None drops it)."""
        files = fixture()
        for key, text in overrides.items():
            name = key.replace("_", "-") + ".yml"
            if text is None:
                files.pop(name)
            else:
                files[name] = text
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in files.items():
                (root / name).write_text(text)
            return run_check(root)

    def check_file(self, name, text):
        """Run the guard on the fixture with one workflow file replaced."""
        return self.check(**{name[: -len(".yml")].replace("-", "_"): text})

    def assert_passes(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def assert_fails(self, result, needle):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(needle, result.stdout)

    def test_fixture_passes(self):
        self.assert_passes(self.check())

    def test_real_workflows_pass(self):
        result = run_check(REAL_WORKFLOWS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_matches_the_allowlist(self):
        files = fixture()
        for name, job in ALLOWED:
            with self.subTest(name=name, job=job):
                self.assertIn(f"  {job}:\n" + RUNS_ON, files[name])

    def test_each_allowed_job_passes(self):
        # Each allowlisted job is compared whitespace-collapsed, so a reflowed guard
        # on that job alone still passes.
        for name, job in ALLOWED:
            with self.subTest(name=name, job=job):
                one_line = "    runs-on: " + " ".join(RUNS_ON.split()[2:]) + "\n"
                text = replace_job_runs_on(fixture()[name], job, one_line)
                self.assert_passes(self.check_file(name, text))

    def test_allowed_job_on_a_hosted_label_fails(self):
        # The allowlist is exact: a job moved back to hosted must leave the list too.
        for name, job in ALLOWED:
            with self.subTest(name=name, job=job):
                files = fixture()
                text = replace_job_runs_on(
                    files[name], job, "    runs-on: ubuntu-latest\n"
                )
                result = self.check_file(name, text)
                self.assert_fails(
                    result, f"{name}: job {job} runs-on is not the guarded expression"
                )

    def test_tampered_guard_on_each_allowed_job_fails(self):
        clause = "      && github.event.pull_request.head.repo.full_name == github.repository\n"
        self.assertIn(clause, RUNS_ON)
        tampered = {
            "or escape": RUNS_ON.replace(
                ")\n      && 'draftforge", " || true)\n      && 'draftforge"
            ),
            "dropped clause": RUNS_ON.replace(clause, ""),
            "other label": RUNS_ON.replace("'draftforge-home'", "'self-hosted'"),
            "swapped labels": RUNS_ON.replace(
                "'draftforge-home' || 'ubuntu-latest'",
                "'ubuntu-latest' || 'draftforge-home'",
            ),
        }
        for how, runs_on in tampered.items():
            self.assertNotEqual(runs_on, RUNS_ON, how)
            for name, job in ALLOWED:
                with self.subTest(how=how, name=name, job=job):
                    files = fixture()
                    text = replace_job_runs_on(files[name], job, runs_on)
                    result = self.check_file(name, text)
                    self.assert_fails(
                        result,
                        f"{name}: job {job} runs-on is not the guarded expression",
                    )

    def test_allowed_job_without_timeout_fails(self):
        for name, job in ALLOWED:
            with self.subTest(name=name, job=job):
                files = fixture()
                old = f"  {job}:\n" + RUNS_ON + "    timeout-minutes: 10\n"
                self.assertIn(old, files[name])
                text = files[name].replace(old, f"  {job}:\n" + RUNS_ON)
                result = self.check_file(name, text)
                self.assert_fails(result, f"{name}: job {job} has no timeout-minutes")

    def test_stale_allowlist_entry_fails(self):
        result = self.check(pr_labeler=None)
        self.assert_fails(
            result, "pr-labeler.yml: allowlisted job label does not exist"
        )
        renamed = fixture()["shellcheck.yml"].replace(
            "  runs-on-guard:\n", "  guard:\n"
        )
        result = self.check(shellcheck=renamed)
        self.assert_fails(
            result, "shellcheck.yml: allowlisted job runs-on-guard does not exist"
        )

    def test_guard_on_a_non_allowlisted_job_fails(self):
        result = self.check(
            other=OTHER.replace("    runs-on: ubuntu-latest\n", RUNS_ON)
        )
        self.assert_fails(result, "other.yml: draftforge-home at jobs lint runs-on")
        self.assert_fails(
            result, "other.yml: job lint runs-on '${{ (vars.SELF_HOSTED_RUNNERS"
        )

    def test_guard_on_a_non_allowlisted_job_in_an_allowed_workflow_fails(self):
        text = PLAYWRIGHT.replace(
            "    if: ${{ !cancelled() }}\n    runs-on: ubuntu-latest\n",
            "    if: ${{ !cancelled() }}\n" + RUNS_ON,
        )
        self.assertNotEqual(text, PLAYWRIGHT)
        result = self.check(playwright=text)
        self.assert_fails(
            result, "playwright.yml: draftforge-home at jobs test runs-on"
        )

    def test_issue_labeler_using_the_guard_fails(self):
        text = ISSUE_LABELER.replace(
            "    runs-on: ubuntu-latest\n", RUNS_ON + "    timeout-minutes: 5\n"
        )
        result = self.check(issue_labeler=text)
        self.assert_fails(
            result, "issue-labeler.yml: draftforge-home at jobs label runs-on"
        )

    def test_allowed_workflow_triggering_on_issues_fails(self):
        text = fixture()["pr-labeler.yml"].replace("on:\n", "on:\n  issues:\n", 1)
        result = self.check(pr_labeler=text)
        self.assert_fails(
            result,
            "pr-labeler.yml: has a job allowed on draftforge-home and triggers on issues",
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
            playwright=PLAYWRIGHT.replace(
                "run: echo prepare", "run: echo draftforge-home"
            )
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
        result = self.check(playwright=replace_job_runs_on(PLAYWRIGHT, "prepare", expr))
        self.assert_fails(result, "job prepare runs-on is not the guarded expression")

    def test_matrix_runs_on_fails(self):
        result = self.check(other=OTHER.replace("ubuntu-latest", "${{ matrix.os }}"))
        self.assert_fails(result, "job lint runs-on '${{ matrix.os }}'")
        expr = "    runs-on: ${{ matrix.os }}\n"
        result = self.check(
            unit_tests=replace_job_runs_on(
                fixture()["unit-tests.yml"], "typecheck", expr
            )
        )
        self.assert_fails(result, "job typecheck runs-on is not the guarded expression")

    def test_runner_group_fails(self):
        result = self.check(
            other=OTHER.replace(
                "runs-on: ubuntu-latest",
                "runs-on:\n      group: home\n      labels: [x]",
            )
        )
        self.assert_fails(result, "job lint runs-on is a runner group")
        group = "    runs-on:\n      group: home\n"
        result = self.check(
            unit_tests=replace_job_runs_on(
                fixture()["unit-tests.yml"], "typecheck", group
            )
        )
        self.assert_fails(result, "job typecheck runs-on is not the guarded expression")

    def test_hosted_label_list_passes(self):
        result = self.check(
            other=OTHER.replace("ubuntu-latest", "[ubuntu-24.04, ubuntu-latest]")
        )
        self.assert_passes(result)

    def test_remote_reusable_workflow_fails(self):
        result = self.check(
            other=OTHER.replace(
                "./.github/workflows/other.yml",
                "someone/else/.github/workflows/x.yml@v1",
            )
        )
        self.assert_fails(result, "job local-call calls reusable workflow")

    def test_allowed_job_as_a_reusable_workflow_call_fails(self):
        files = fixture()
        old = (
            "  label:\n"
            + RUNS_ON
            + "    timeout-minutes: 10\n    steps:\n      - run: echo label\n"
        )
        self.assertIn(old, files["pr-labeler.yml"])
        text = files["pr-labeler.yml"].replace(
            old, "  label:\n    uses: someone/else/.github/workflows/x.yml@v1\n"
        )
        result = self.check(pr_labeler=text)
        self.assert_fails(
            result, "pr-labeler.yml: job label runs-on is not the guarded expression"
        )

    def test_runs_on_reflowed_passes(self):
        one_line = "    runs-on: " + " ".join(RUNS_ON.split()[2:]) + "\n"
        self.assertNotEqual(one_line, RUNS_ON)
        result = self.check(
            playwright=replace_job_runs_on(PLAYWRIGHT, "prepare", one_line)
        )
        self.assert_passes(result)

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

    def test_home_prepare_elsewhere_must_match(self):
        text = fixture()["changelog.yml"].replace(
            "jobs:\n",
            "env:\n  HOME_PREPARE: ${{ vars.SELF_HOSTED_RUNNERS == 'true' }}\njobs:\n",
        )
        result = self.check(changelog=text)
        self.assert_fails(
            result, "changelog.yml: env.HOME_PREPARE is not the runs-on guard"
        )

    def test_test_jobs_may_need_prepare(self):
        # #787: test jobs wait for prepare (needs + !cancelled()); that is allowed.
        self.assertIn("needs: prepare", PLAYWRIGHT)
        self.assertEqual(self.check().returncode, 0)

    def test_pull_request_target_trigger_fails(self):
        result = self.check(
            playwright=PLAYWRIGHT.replace("on:\n", "on:\n  pull_request_target:\n", 1)
        )
        self.assert_fails(result, "triggers on pull_request_target")

    def test_workflow_run_trigger_fails(self):
        text = fixture()["changelog.yml"].replace(
            "on:\n", "on:\n  workflow_run:\n    workflows: [Other]\n", 1
        )
        result = self.check(changelog=text)
        self.assert_fails(
            result,
            "changelog.yml: has a job allowed on draftforge-home and triggers on workflow_run",
        )

    def test_pull_request_target_workflow_cannot_reach_self_hosted(self):
        target = OTHER.replace("  pull_request:\n", "  pull_request_target:\n").replace(
            "ubuntu-latest", "self-hosted"
        )
        result = self.check(other=target)
        self.assert_fails(result, "job lint runs-on 'self-hosted'")


if __name__ == "__main__":
    unittest.main()
