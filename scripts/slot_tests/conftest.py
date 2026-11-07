import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.slot_tests._helpers import FakeHost  # noqa: E402


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in list(os.environ):
        if k.startswith(("DF_", "COMPOSE_")) or k in ("GITHUB_ACTIONS", "RUNNER_TEMP", "GITHUB_WORKSPACE"):
            monkeypatch.delenv(k)


@pytest.fixture
def fake_host(tmp_path: Path) -> FakeHost:
    return FakeHost(tmp_path / "git-common")


@pytest.fixture
def make_worktree(tmp_path: Path, fake_host: FakeHost) -> Callable[[str], Path]:
    def make(name: str) -> Path:
        p = tmp_path / name
        (p / "docker").mkdir(parents=True)
        p = p.resolve()
        fake_host.worktrees.add(p)
        return p

    return make
