import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from app.tests.test_settings_env_overrides import _reload
from backend.settings import is_docker


class IsDockerTests(SimpleTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "proc/1").mkdir(parents=True)
        (self.root / "run").mkdir()

    def test_dockerenv(self) -> None:
        (self.root / ".dockerenv").touch()
        self.assertTrue(is_docker(self.root))

    def test_podman_containerenv(self) -> None:
        (self.root / "run/.containerenv").touch()
        self.assertTrue(is_docker(self.root))

    def test_docker_cgroup(self) -> None:
        (self.root / "proc/1/cgroup").write_text("12:pids:/docker/abc123\n")
        self.assertTrue(is_docker(self.root))

    def test_no_markers(self) -> None:
        (self.root / "proc/1/cgroup").write_text("0::/\n")
        self.assertFalse(is_docker(self.root))

    def test_no_cgroup_file(self) -> None:
        self.assertFalse(is_docker(self.root))

    def test_redis_host_env_overrides_detection(self) -> None:
        mod = _reload({"REDIS_HOST": "cache.example"})
        self.assertEqual(mod.REDIS_HOST, "cache.example")
