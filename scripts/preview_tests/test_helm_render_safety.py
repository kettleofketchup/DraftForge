import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.preview_tests import _util

SCRIPT = _util.REPO_ROOT / "scripts" / "helm_render_safety.sh"
CHART = _util.REPO_ROOT / "helm"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class RenderSafetyTest(unittest.TestCase):
    def setUp(self):
        _util.require(_util.which("yq"), "yq")
        self.env = {**os.environ, **GIT_ENV}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        shutil.copytree(CHART, self.repo / "helm", symlinks=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")

    def check(self, target=None):
        return subprocess.run(["bash", str(SCRIPT), str(target or self.repo / "helm")],
                              env=self.env, capture_output=True, text=True)

    def assertViolation(self, needle):
        self.commit()
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout + r.stderr)

    def test_clean_chart_passes(self):
        self.commit()
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_chart_dependencies_fail(self):
        with open(self.repo / "helm" / "Chart.yaml", "a") as f:
            f.write("dependencies:\n  - name: x\n    version: 1.0.0\n"
                    "    repository: https://example.invalid\n")
        self.assertViolation("dependencies")

    def test_charts_dir_fails(self):
        (self.repo / "helm" / "charts").mkdir()
        (self.repo / "helm" / "charts" / "keep").write_text("")
        self.assertViolation("charts/")

    def test_argocd_source_fails(self):
        (self.repo / "helm" / ".argocd-source.yaml").write_text("helm: {}\n")
        self.assertViolation(".argocd-source.yaml")

    def test_kustomization_fails(self):
        (self.repo / "helm" / "templates" / "kustomization.yaml").write_text("resources: []\n")
        self.assertViolation("kustomization.yaml")

    def test_symlink_fails(self):
        os.symlink("values.yaml", self.repo / "helm" / "link.yaml")
        self.assertViolation("link.yaml")

    def test_gitmodules_fails(self):
        (self.repo / ".gitmodules").write_text(
            '[submodule "sub"]\n\tpath = sub\n\turl = https://example.invalid/x.git\n')
        self.assertViolation(".gitmodules")

    def test_gitlink_fails(self):
        self.commit()
        sha = self.git("rev-parse", "HEAD").strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},sub")
        self.git("commit", "-q", "-m", "gitlink")
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("160000", r.stdout + r.stderr)

    def test_not_a_git_repo_fails(self):
        with tempfile.TemporaryDirectory() as plain:
            shutil.copytree(CHART, Path(plain) / "helm", symlinks=True)
            r = self.check(Path(plain) / "helm")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not inside a git repository", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
