"""Structure and behaviour tests for the preview GitHub Actions workflows.

Workflows are read with `yq -o=json`. Where a step's shell script
carries real logic (tag, exists check, comments) the script is executed with
shimmed `docker`/`gh` binaries, so the test exercises behaviour and not only
its spelling.
"""
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.preview_tests import _util

WORKFLOW_DIR = _util.REPO_ROOT / ".github" / "workflows"
WORKFLOWS_ADDED = ["helm-chart.yml", "preview-images.yml", "preview-queue.yml"]

IMAGES = "preview-images.yml"
QUEUE = "preview-queue.yml"
PREVIEW_REPO = "ghcr.io/kettleofketchup/draftforge-preview/"
PROD_REPO = "ghcr.io/kettleofketchup/draftforge/"
FLOOR_MARKER = "<!-- preview-floor -->"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
RUN_URL = "https://github.com/kettleofketchup/DraftForge/actions/runs/42"


def load(name: str) -> dict:
    """Return the workflow `.github/workflows/<name>` as a dict (via yq)."""
    _util.require(_util.which("yq"), "yq")
    path = WORKFLOW_DIR / name
    if not path.is_file():
        raise AssertionError(f"workflow {path} does not exist")
    out = subprocess.run(["yq", "-o=json", ".", str(path)], capture_output=True,
                         text=True, check=True).stdout
    return json.loads(out)


def all_steps(wf: dict):
    for job in wf.get("jobs", {}).values():
        yield from job.get("steps", [])


def all_uses(wf: dict):
    for job in wf.get("jobs", {}).values():
        if "uses" in job:
            yield job["uses"]
        for step in job.get("steps", []):
            if "uses" in step:
                yield step["uses"]


def strings_with_paths(node, path=()):
    """Yield (key path, value) for every string scalar in a JSON tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from strings_with_paths(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from strings_with_paths(value, path + (i,))
    elif isinstance(node, str):
        yield path, node


def step_using(steps, action: str) -> dict:
    found = [s for s in steps if s.get("uses", "").startswith(action + "@")]
    if len(found) != 1:
        raise AssertionError(f"expected one step using {action}, found {len(found)}")
    return found[0]


def step_index(steps, pred) -> int:
    for i, step in enumerate(steps):
        if pred(step):
            return i
    raise AssertionError("step not found")


def step_by_id(steps, step_id: str) -> dict:
    return steps[step_index(steps, lambda s: s.get("id") == step_id)]


def make_shim(bindir: Path, name: str, body: str) -> None:
    path = bindir / name
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


GH_SHIM = """import json, os, sys
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if "-X" not in sys.argv:
    sys.stdout.write(os.environ.get("GH_FAKE_OUT", ""))
"""

DOCKER_SHIM = """import os, sys
sys.stderr.write(os.environ.get("DOCKER_FAKE_ERR", ""))
sys.exit(int(os.environ.get("DOCKER_FAKE_RC", "0")))
"""


def run_step(step: dict, env: dict, cwd=None):
    """Run a step's `run:` script the way Actions does (bash -eo pipefail).

    Returns (CompletedProcess, GITHUB_OUTPUT text, list of logged gh argv).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bindir = tmp / "bin"
        bindir.mkdir()
        make_shim(bindir, "gh", GH_SHIM)
        make_shim(bindir, "docker", DOCKER_SHIM)
        out_file = tmp / "github_output"
        out_file.touch()
        gh_log = tmp / "gh.log"
        gh_log.touch()
        script = tmp / "step.sh"
        script.write_text(step["run"])
        full_env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(out_file),
            "GH_LOG": str(gh_log),
        }
        full_env.update(env)
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            env=full_env, cwd=cwd or tmp, capture_output=True, text=True)
        calls = [json.loads(line) for line in gh_log.read_text().splitlines()]
        return proc, out_file.read_text(), calls


class PreviewImagesStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = load(IMAGES)
        cls.build = cls.wf["jobs"]["build"]
        cls.report = cls.wf["jobs"]["report"]
        cls.steps = cls.build["steps"]
        cls.build_push = step_using(cls.steps, "docker/build-push-action")

    def test_images_author_gate_exact(self):
        cond = self.build["if"]
        self.assertIn(
            "contains(format(',{0},', vars.PREVIEW_AUTHORS || 'kettleofketchup'), "
            "format(',{0},', github.event.pull_request.user.login))", cond)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository", cond)

    def test_images_concurrency_per_leg(self):
        conc = self.build["concurrency"]
        self.assertIn("matrix.name", conc["group"])
        self.assertIn("github.event.pull_request.number", conc["group"])
        self.assertIn("github.event.pull_request.head.sha", conc["group"])
        self.assertIs(conc["cancel-in-progress"], False)

    def test_images_matrix_legs(self):
        legs = {leg["name"]: leg for leg in self.build["strategy"]["matrix"]["include"]}
        self.assertEqual(set(legs), {"backend", "frontend"})
        self.assertEqual((legs["backend"]["context"], legs["backend"]["file"],
                          legs["backend"]["target"]), (".", "backend/Dockerfile", "runtime"))
        self.assertEqual((legs["frontend"]["context"], legs["frontend"]["file"],
                          legs["frontend"]["target"]),
                         ("frontend", "frontend/Dockerfile", "runtime"))
        self.assertEqual(
            legs["frontend"]["args"].split(),
            ["VITE_PREVIEW_TEST_FEATURES=true", "VITE_SENTRY_ENABLED=false"],
        )
        self.assertEqual(legs["backend"]["args"], "")
        self.assertIs(self.build["strategy"]["fail-fast"], False)
        self.assertEqual(self.build_push["with"]["build-args"], "${{ matrix.args }}")

    def test_images_push_and_provenance(self):
        with_ = self.build_push["with"]
        self.assertIs(with_["push"], True)
        self.assertIs(with_["provenance"], False)
        self.assertNotIn("cache-to", with_)
        for path, _ in strings_with_paths(self.wf):
            self.assertNotIn("cache-to", path)

    def test_no_build_cache_and_no_prod_path(self):
        self.assertNotIn("cache-from", self.build_push["with"])
        for path, value in strings_with_paths(self.wf):
            self.assertNotIn("cache-from", path)
            self.assertNotIn(PROD_REPO, value, path)

    def test_build_tags_use_tag_output(self):
        self.assertEqual(
            self.build_push["with"]["tags"],
            "ghcr.io/kettleofketchup/draftforge-preview/${{ matrix.name }}:"
            "${{ steps.tag.outputs.tag }}")

    def test_build_labels(self):
        labels = self.build_push["with"]["labels"].splitlines()
        self.assertEqual(labels, [
            "org.opencontainers.image.revision=${{ github.event.pull_request.head.sha }}",
            "org.opencontainers.image.source=https://github.com/kettleofketchup/DraftForge",
        ])

    def test_floor_and_exists_steps(self):
        floor_i = step_index(self.steps, lambda s: s.get("id") == "floor")
        build_i = self.steps.index(self.build_push)
        self.assertLess(floor_i, build_i)
        floor = self.steps[floor_i]
        self.assertIn("backend/backend/env_utils.py", floor["run"])
        self.assertIn("ARG VITE_PREVIEW_TEST_FEATURES", floor["run"])
        exists_i = step_index(self.steps, lambda s: s.get("id") == "exists")
        self.assertLess(exists_i, build_i)
        self.assertIn("docker buildx imagetools inspect", self.steps[exists_i]["run"])
        buildx = step_using(self.steps, "docker/setup-buildx-action")
        for step in (buildx, self.build_push):
            self.assertIn("steps.exists.outputs.found != 'true'", step["if"])
        login = step_using(self.steps, "docker/login-action")
        self.assertLess(self.steps.index(login), exists_i)
        self.assertEqual(login["with"]["registry"], "ghcr.io")

    def test_floor_sets_output_and_fails(self):
        floor = step_by_id(self.steps, "floor")
        self.assertEqual(self.build["outputs"]["floor_ok"], "${{ steps.floor.outputs.floor_ok }}")
        with tempfile.TemporaryDirectory() as tmp:
            proc, out, _ = run_step(floor, {}, cwd=tmp)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("floor_ok=false", out.split())
            (Path(tmp) / "backend" / "backend").mkdir(parents=True)
            (Path(tmp) / "backend" / "backend" / "env_utils.py").touch()
            (Path(tmp) / "frontend").mkdir()
            (Path(tmp) / "frontend" / "Dockerfile").write_text(
                "FROM x\nARG VITE_PREVIEW_TEST_FEATURES=false\n")
            proc, out, _ = run_step(floor, {}, cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("floor_ok=true", out.split())

    def test_report_states(self):
        self.assertEqual(self.report["needs"], "build")
        self.assertEqual(self.report["if"], "always() && needs.build.result != 'skipped'")
        steps = self.report["steps"]
        comments = [s for s in steps if "issues/$PR/comments" in s.get("run", "")]
        self.assertEqual(len(comments), 2)
        for step in comments:
            self.assertIn("needs.build.result == 'failure'", step["if"])
        # Every step is gated on success or failure, so `cancelled` posts nothing.
        for step in steps:
            cond = step.get("if", "")
            self.assertRegex(cond, r"needs\.build\.result == '(success|failure)'")
            self.assertNotIn("cancelled", cond)
            self.assertNotIn("always()", cond)
        status = step_by_id(steps, "status")
        self.assertEqual(
            status["if"],
            "needs.build.result == 'success' || needs.build.result == 'failure'")
        self.assertEqual(status["env"]["STATE"], "${{ needs.build.result }}")

    def test_tag_is_sha7(self):
        tag = step_by_id(self.steps, "tag")
        self.assertIn("${HEAD_SHA:0:7}", tag["run"])
        self.assertIn("pr-${PR}-", tag["run"])
        self.assertNotIn(":0:8", tag["run"])
        self.assertEqual(self.build["outputs"]["tag"], "${{ steps.tag.outputs.tag }}")
        proc, out, _ = run_step(tag, {"PR": "12", "HEAD_SHA": HEAD_SHA})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.split(), ["tag=pr-12-0123456"])

    def test_status_context_and_description(self):
        status = step_by_id(self.report["steps"], "status")
        self.assertIn("context=preview-images", status["run"])
        self.assertIn('description="$TAG"', status["run"])
        self.assertEqual(status["env"]["TAG"], "${{ needs.build.outputs.tag }}")
        proc, _, calls = run_step(status, {
            "GH_REPO": "kettleofketchup/DraftForge", "HEAD_SHA": HEAD_SHA,
            "TAG": "pr-12-0123456", "STATE": "failure", "RUN_URL": RUN_URL})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, [[
            "api", "-X", "POST", f"repos/kettleofketchup/DraftForge/statuses/{HEAD_SHA}",
            "-f", "context=preview-images", "-f", "state=failure",
            "-f", "description=pr-12-0123456", "-f", f"target_url={RUN_URL}"]])

    def test_checkout_uses_head_sha(self):
        checkout = step_using(self.steps, "actions/checkout")
        self.assertEqual(checkout["with"]["ref"], "${{ github.event.pull_request.head.sha }}")

    def test_build_timeout(self):
        self.assertEqual(self.build["timeout-minutes"], 45)

    def test_images_permissions(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertEqual(self.build["permissions"], {"contents": "read", "packages": "write"})
        self.assertEqual(self.report["permissions"], {"statuses": "write", "issues": "write"})

    def test_triggers(self):
        self.assertEqual(self.wf["on"],
                         {"pull_request": {"types": ["opened", "synchronize", "reopened"]}})


class ExistsCheckTest(unittest.TestCase):
    """Run the exists step against a fake `docker` with each registry answer."""

    @classmethod
    def setUpClass(cls):
        cls.step = step_by_id(load(IMAGES)["jobs"]["build"]["steps"], "exists")

    def run_exists(self, rc: int, err: str):
        return run_step(self.step, {
            "REF": PREVIEW_REPO + "backend:pr-12-0123456",
            "DOCKER_FAKE_RC": str(rc), "DOCKER_FAKE_ERR": err})

    def test_exists_distinguishes_not_found(self):
        run = self.step["run"]
        self.assertNotIn("|| echo found=false", run)
        self.assertNotIn("|| echo \"found=false\"", run)
        lines = [line.strip() for line in run.splitlines() if line.strip()]
        guard = [i for i, line in enumerate(lines)
                 if "grep -qiE 'not found|MANIFEST_UNKNOWN|NAME_UNKNOWN'" in line]
        self.assertEqual(len(guard), 1)
        false_lines = [i for i, line in enumerate(lines) if "found=false" in line]
        self.assertEqual(false_lines, [guard[0] + 1])
        self.assertIn("exit 1", lines[guard[0] + 2:])

    def test_exists_found(self):
        proc, out, _ = self.run_exists(0, "")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.split(), ["found=true"])

    def test_exists_not_found_variants(self):
        for err in ("ERROR: ghcr.io/x:pr-12-0123456: not found",
                    "MANIFEST_UNKNOWN: manifest unknown",
                    "error: NAME_UNKNOWN: repository name not known to registry"):
            with self.subTest(err=err):
                proc, out, _ = self.run_exists(1, err)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(out.split(), ["found=false"])

    def test_exists_other_errors_fail(self):
        for err in ("unexpected status: 500 Internal Server Error",
                    "toomanyrequests: rate limit exceeded",
                    "unexpected status: 401 Unauthorized"):
            with self.subTest(err=err):
                proc, out, _ = self.run_exists(1, err)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out, "")
                self.assertIn(err, proc.stderr)


class ReportCommentTest(unittest.TestCase):
    """Run the report's comment steps against a fake `gh`."""

    ENV = {"GH_REPO": "kettleofketchup/DraftForge", "PR": "12",
           "HEAD_SHA": HEAD_SHA, "RUN_URL": RUN_URL}

    @classmethod
    def setUpClass(cls):
        steps = load(IMAGES)["jobs"]["report"]["steps"]
        comments = [s for s in steps if "issues/$PR/comments" in s.get("run", "")]
        cls.floor = next(s for s in comments if "floor_ok == 'false'" in s["if"])
        cls.failed = next(s for s in comments if "floor_ok != 'false'" in s["if"])

    @staticmethod
    def posted_bodies(calls):
        bodies = []
        for argv in calls:
            if "-X" in argv:
                body = [a for a in argv if a.startswith("body=")]
                bodies.append(body[0][len("body="):])
        return bodies

    def test_build_failure_comment_verbatim(self):
        proc, _, calls = run_step(self.failed, self.ENV)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4],
                         ["api", "-X", "POST", "repos/kettleofketchup/DraftForge/issues/12/comments"])
        self.assertEqual(self.posted_bodies(calls), [
            "Preview image build failed for commit `0123456`. The preview (if any) keeps "
            "serving the previous commit's backend and frontend; the celery worker may be "
            f"down until the next good commit. See {RUN_URL}."])

    def test_floor_comment_verbatim(self):
        proc, _, calls = run_step(self.floor, dict(self.ENV, GH_FAKE_OUT="hello\nother\n"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.posted_bodies(calls), [
            FLOOR_MARKER + "\nPreview images were not built for commit `0123456`: this "
            "branch predates preview support. Rebase on main to get a preview."])

    def test_floor_comment_deduplicated(self):
        run = self.floor["run"]
        list_at = run.index("issues/$PR/comments")
        self.assertIn("--paginate", run)
        self.assertIn("--jq", run)
        self.assertIn(FLOOR_MARKER, run)
        self.assertLess(list_at, run.index("-X POST"))
        proc, _, calls = run_step(self.floor, dict(
            self.ENV, GH_FAKE_OUT=f"first\n{FLOOR_MARKER}\nPreview images were not built\n"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("-X", calls[0])
        self.assertIn("--paginate", calls[0])
        self.assertIn("repos/kettleofketchup/DraftForge/issues/12/comments", calls[0])


GH_EXIT_SHIM = """import json, os, sys
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.stderr.write(os.environ.get("GH_FAKE_ERR", ""))
sys.exit(int(os.environ.get("GH_FAKE_RC", "0")))
"""


class PreviewQueueStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = load(QUEUE)
        cls.text = (WORKFLOW_DIR / QUEUE).read_text()
        cls.release = cls.wf["jobs"]["release-closed"]
        cls.reconcile = cls.wf["jobs"]["reconcile"]

    def test_queue_never_checks_out_pr_code(self):
        self.assertNotIn("head.sha", self.text)
        self.assertNotIn("head.ref", self.text)
        self.assertNotIn("github.head_ref", self.text)
        # release-closed only calls the API; it checks nothing out.
        self.assertEqual([s for s in self.release["steps"] if "uses" in s], [])

    def test_queue_checkout_ref(self):
        checkout = step_using(self.reconcile["steps"], "actions/checkout")
        self.assertEqual(checkout["with"]["ref"],
                         "${{ github.event.repository.default_branch || 'main' }}")
        self.assertIs(checkout["with"]["persist-credentials"], False)
        run = [s for s in self.reconcile["steps"] if "run" in s]
        self.assertEqual([s["run"].strip() for s in run], ["python3 -I scripts/preview_queue.py"])

    def test_release_closed_tolerates_404(self):
        (step,) = [s for s in self.release["steps"] if "run" in s]
        self.assertIn("HTTP 404", step["run"])
        self.assertIn(
            'out=$(gh api -X DELETE "repos/$GH_REPO/issues/$PR/labels/preview-env" 2>&1) || '
            "{ grep -q 'HTTP 404' <<<\"$out\" || { echo \"$out\"; exit 1; }; }", step["run"])
        cases = [(0, "", True), (1, "gh: Not Found (HTTP 404)", True),
                 (1, "gh: Server Error (HTTP 500)", False),
                 (1, "gh: Forbidden (HTTP 403)", False)]
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp)
            make_shim(bindir, "gh", GH_EXIT_SHIM)
            for rc, err, ok in cases:
                with self.subTest(rc=rc, err=err):
                    proc, _, calls = run_step(step, {
                        "PATH": f"{bindir}:{os.environ['PATH']}",
                        "GH_REPO": "kettleofketchup/DraftForge", "PR": "12",
                        "GH_FAKE_RC": str(rc), "GH_FAKE_ERR": err})
                    self.assertEqual(proc.returncode == 0, ok, proc.stdout + proc.stderr)
                    if not ok:
                        self.assertIn(err, proc.stdout)
                    self.assertEqual(calls, [[
                        "api", "-X", "DELETE",
                        "repos/kettleofketchup/DraftForge/issues/12/labels/preview-env"]])

    def test_queue_triggers(self):
        on = self.wf["on"]
        self.assertEqual(set(on), {"workflow_run", "pull_request_target", "schedule",
                                   "workflow_dispatch"})
        self.assertEqual(on["workflow_run"],
                         {"workflows": ["preview-images"], "types": ["completed"]})
        self.assertEqual(on["pull_request_target"],
                         {"types": ["closed", "reopened", "labeled", "unlabeled"]})
        self.assertNotIn("branches", on["pull_request_target"])
        self.assertEqual(on["schedule"], [{"cron": "*/10 * * * *"}])
        self.assertIn(on["workflow_dispatch"], ({}, None))
        self.assertEqual(self.wf["permissions"], {})

    def test_reconcile_wiring(self):
        self.assertEqual(self.reconcile["needs"], "release-closed")
        self.assertEqual(self.reconcile["if"], "always()")
        self.assertEqual(self.reconcile["concurrency"],
                         {"group": "preview-queue", "cancel-in-progress": False})
        self.assertEqual(self.reconcile["permissions"], {
            "contents": "read", "issues": "write", "pull-requests": "write",
            "statuses": "write"})
        self.assertNotIn("concurrency", self.release)
        self.assertEqual(self.release["permissions"], {"pull-requests": "write"})
        self.assertEqual(
            self.release["if"],
            "github.event_name == 'pull_request_target' && github.event.action == 'closed'")

    def test_queue_env(self):
        self.assertEqual(self.release["env"], {
            "GH_TOKEN": "${{ github.token }}",
            "GH_REPO": "${{ github.repository }}",
            "PR": "${{ github.event.pull_request.number }}",
        })
        self.assertEqual(self.reconcile["env"], {
            "GH_TOKEN": "${{ github.token }}",
            "GH_REPO": "${{ github.repository }}",
            "CAP": "${{ vars.PREVIEW_CAP || '0' }}",
            "PREVIEW_AUTHORS": "${{ vars.PREVIEW_AUTHORS || 'kettleofketchup' }}",
            "PREVIEW_IDLE_DAYS": "${{ vars.PREVIEW_IDLE_DAYS || '7' }}",
            "PREVIEW_REQUIRE_VERIFIED": "${{ vars.PREVIEW_REQUIRE_VERIFIED || 'false' }}",
            "CLOSED_PR": "${{ github.event.action == 'closed' && "
                         "github.event.pull_request.number || '' }}",
        })


class HelmChartWorkflowTest(unittest.TestCase):
    def test_helm_chart_watches_and_lints_queue_workflow(self):
        wf = load("helm-chart.yml")
        path = ".github/workflows/" + QUEUE
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertIn(path, wf["on"][event]["paths"])
        (lint,) = [s for s in all_steps(wf) if s.get("name") == "actionlint"]
        self.assertIn(path, lint["run"].split())


class WorkflowHygieneTest(unittest.TestCase):
    """Hygiene rules for every workflow this project adds."""

    def each(self):
        for name in WORKFLOWS_ADDED:
            with self.subTest(workflow=name):
                yield load(name)

    def test_checkout_hygiene(self):
        for wf in self.each():
            checkouts = [s for s in all_steps(wf)
                         if s.get("uses", "").startswith("actions/checkout@")]
            for step in checkouts:
                self.assertIs(step.get("with", {}).get("persist-credentials"), False, step)

    def test_no_inline_event_data(self):
        for wf in self.each():
            for step in all_steps(wf):
                run = step.get("run", "")
                self.assertNotIn("${{ github.event.", run)
                self.assertNotIn("${{ github.head_ref", run)

    def test_uses_sha_pinned(self):
        for wf in self.each():
            for uses in all_uses(wf):
                self.assertRegex(uses, r"@[0-9a-f]{40}$")
        for name in WORKFLOWS_ADDED:
            with self.subTest(workflow=name, check="version comment"):
                text = (WORKFLOW_DIR / name).read_text()
                for line in re.findall(r"^\s*(?:- )?uses:.*$", text, re.M):
                    self.assertRegex(line, r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$")

    def test_top_level_permissions_minimal(self):
        for wf in self.each():
            self.assertIn(wf.get("permissions"), ({}, {"contents": "read"}))


if __name__ == "__main__":
    unittest.main()
