"""Unit tests for backend.container.in_container against a fake filesystem root."""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from backend.container import in_container


class InContainerTests(SimpleTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _touch(self, rel: str, content: str = "") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_bare_host_is_not_a_container(self) -> None:
        self.assertIs(in_container(self.root), False)

    def test_host_cgroup_v2_is_not_a_container(self) -> None:
        self._touch("proc/1/cgroup", "0::/init.scope\n")
        self.assertIs(in_container(self.root), False)

    def test_dockerenv_marker(self) -> None:
        self._touch(".dockerenv")
        self.assertIs(in_container(self.root), True)

    def test_podman_containerenv_marker(self) -> None:
        self._touch("run/.containerenv")
        self.assertIs(in_container(self.root), True)

    def test_docker_cgroup_v1(self) -> None:
        self._touch("proc/1/cgroup", "12:pids:/docker/abc123\n")
        self.assertIs(in_container(self.root), True)

    def test_podman_cgroup_v1(self) -> None:
        self._touch("proc/1/cgroup", "12:pids:/machine.slice/libpod-abc123.scope\n")
        self.assertIs(in_container(self.root), True)
