import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.preview_tests import _util

SCRIPT = _util.REPO_ROOT / "scripts" / "helm_version_bump_check.sh"
MESSAGE = "helm/ changed but Chart.yaml version was not bumped"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}

CHART = "apiVersion: v2\nname: draftforge\ntype: application\nversion: {version}\n"


class VersionBumpCheckTest(unittest.TestCase):
    def setUp(self):
        _util.require(_util.which("yq"), "yq")
        self.env = {**os.environ, **GIT_ENV}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD").strip()

    def base_with_chart(self):
        self.write("README.md", "app\n")
        self.write("helm/Chart.yaml", CHART.format(version="0.1.0"))
        self.write("helm/templates/backend.yaml", "kind: Deployment\n")
        return self.commit("base")

    def check(self, base):
        return subprocess.run(["bash", str(SCRIPT), base], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def test_unchanged_passes(self):
        base = self.base_with_chart()
        self.write("README.md", "app, edited\n")
        self.commit("app change only")
        r = self.check(base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bumped_passes(self):
        base = self.base_with_chart()
        self.write("helm/templates/backend.yaml", "kind: Deployment\n# changed\n")
        self.write("helm/Chart.yaml", CHART.format(version="0.1.1"))
        self.commit("chart change with bump")
        r = self.check(base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_not_bumped_fails(self):
        base = self.base_with_chart()
        self.write("helm/templates/backend.yaml", "kind: Deployment\n# changed\n")
        self.commit("chart change without bump")
        r = self.check(base)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(MESSAGE, r.stdout + r.stderr)

    def test_downgrade_fails(self):
        base = self.base_with_chart()
        self.write("helm/templates/backend.yaml", "kind: Deployment\n# changed\n")
        self.write("helm/Chart.yaml", CHART.format(version="0.0.9"))
        self.commit("chart change with a lower version")
        r = self.check(base)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("version went down", r.stdout + r.stderr)

    def test_numeric_not_lexical_order(self):
        # 0.10.0 sorts before 0.9.0 lexically but is the higher version.
        self.write("README.md", "app\n")
        self.write("helm/Chart.yaml", CHART.format(version="0.9.0"))
        self.write("helm/templates/backend.yaml", "kind: Deployment\n")
        base = self.commit("base")
        self.write("helm/templates/backend.yaml", "kind: Deployment\n# changed\n")
        self.write("helm/Chart.yaml", CHART.format(version="0.10.0"))
        self.commit("bump past 0.9")
        r = self.check(base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tests_and_readme_only_pass_without_bump(self):
        # helm/tests/ is .helmignored and README.md does not render, so neither
        # changes what a deployer renders.
        base = self.base_with_chart()
        self.write("helm/tests/backend_test.yaml", "suite: x\n")
        self.write("helm/README.md", "docs\n")
        self.commit("tests and docs only")
        r = self.check(base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tests_plus_template_change_still_needs_bump(self):
        base = self.base_with_chart()
        self.write("helm/tests/backend_test.yaml", "suite: x\n")
        self.write("helm/templates/backend.yaml", "kind: Deployment\n# changed\n")
        self.commit("tests and template")
        r = self.check(base)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(MESSAGE, r.stdout + r.stderr)

    def test_base_absent_counts_as_bumped(self):
        self.write("README.md", "app\n")
        base = self.commit("base without chart")
        self.write("helm/Chart.yaml", CHART.format(version="0.1.0"))
        self.write("helm/templates/backend.yaml", "kind: Deployment\n")
        self.commit("add chart")
        r = self.check(base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
