"""ci::prefetch-start runs the image and test-DB pulls in the background; ci::prefetch-wait joins them."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")

DOCKER_STUB = """#!/usr/bin/env bash
[[ "${{1-}}" == "--version" ]] && {{ echo "Docker version 27.3.1"; exit 0; }}
exit {status}
"""


def just(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    assert JUST is not None
    return subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def stub_env(tmp_path: Path, status: int) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(DOCKER_STUB.format(status=status))
    stub.chmod(0o755)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
    }


def test_prefetch_success_is_joined(tmp_path: Path) -> None:
    env = stub_env(tmp_path, 0)
    started = just(env, "ci::prefetch-start")
    assert started.returncode == 0, started.stderr
    for name in ("images", "db"):
        waited = just(env, "ci::prefetch-wait", name, "60")
        assert waited.returncode == 0, waited.stdout + waited.stderr
        assert f"prefetch {name}: ok" in waited.stdout


def test_prefetch_failure_propagates(tmp_path: Path) -> None:
    env = stub_env(tmp_path, 1)
    assert just(env, "ci::prefetch-start").returncode == 0
    waited = just(env, "ci::prefetch-wait", "images", "60")
    assert waited.returncode == 1
    assert "prefetch images: failed" in waited.stderr


def test_wait_times_out_without_start(tmp_path: Path) -> None:
    env = stub_env(tmp_path, 0)
    (Path(env["RUNNER_TEMP"]) / "df-prefetch").mkdir()
    waited = just(env, "ci::prefetch-wait", "images", "1")
    assert waited.returncode == 1
    assert "still running" in waited.stderr
