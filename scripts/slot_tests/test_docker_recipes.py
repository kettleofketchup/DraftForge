"""Run docker::buildx against a recording docker stub that reports Docker or podman."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")
IMAGE = "ghcr.io/kettleofketchup/draftforge/nginx"

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")

DOCKER_STUB = """#!/usr/bin/env bash
if [[ "${{1-}}" == "--version" ]]; then
    echo "{version}"
    exit 0
fi
printf '%s\\0' "$@" > {log}
"""


def build(tmp_path: Path, version: str, *flags: str) -> list[str]:
    assert JUST is not None
    log = tmp_path / "argv"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(DOCKER_STUB.format(version=version, log=log))
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "docker::nginx::build", *flags],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return log.read_bytes().decode().split("\0")[:-1]


DOCKER = "Docker version 27.3.1, build ce12230"
PODMAN = "podman version 6.1.4"


def test_docker_build_uses_registry_cache(tmp_path: Path) -> None:
    argv = build(tmp_path, DOCKER)
    assert argv[:2] == ["buildx", "build"]
    assert "--cache-from" in argv
    assert (
        argv[argv.index("--cache-from") + 1] == f"type=registry,ref={IMAGE}:buildcache"
    )
    assert "--load" in argv


def test_docker_push_writes_registry_cache(tmp_path: Path) -> None:
    argv = build(tmp_path, DOCKER, "--push")
    assert (
        argv[argv.index("--cache-to") + 1]
        == f"type=registry,ref={IMAGE}:buildcache,mode=max"
    )
    assert "--push" in argv


@pytest.mark.parametrize("flags", [(), ("--push",)])
def test_podman_build_skips_registry_cache(
    tmp_path: Path, flags: tuple[str, ...]
) -> None:
    argv = build(tmp_path, PODMAN, *flags)
    assert argv[:2] == ["buildx", "build"]
    assert "--cache-from" not in argv
    assert "--cache-to" not in argv
    assert argv[-1] == "nginx"


TEST_DB_DOCKER_STUB = """#!/usr/bin/env bash
if [[ "${{1-}}" == "--version" ]]; then
    echo "{version}"
    exit 0
fi
if [[ "${{1-}} ${{2-}}" == "image inspect" ]]; then
    exit 1
fi
if [[ "${{1-}}" == "build" ]]; then
    printf '%s\\0' "$@" > {log}
fi
"""


def build_test_db(tmp_path: Path, version: str) -> list[str]:
    assert JUST is not None
    log = tmp_path / "argv"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(TEST_DB_DOCKER_STUB.format(version=version, log=log))
    python = bin_dir / "python"
    python.write_text("#!/usr/bin/env bash\n")
    for stub in (docker, python):
        stub.chmod(0o755)
    db_dir = tmp_path / "dbs"
    db_dir.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "DF_JUST_PYTHON": str(python),
        "DF_TEST_DB_FILE": str(tmp_path / "test.db.sqlite3"),
        "DF_DB_DIR": str(db_dir),
    }
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "docker::db::build"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return log.read_bytes().decode().split("\0")[:-1]


def test_test_db_build_loads_the_image_into_docker(tmp_path: Path) -> None:
    # A docker-container buildx builder keeps the result in its cache without --load.
    assert "--load" in build_test_db(tmp_path, DOCKER)


def test_test_db_build_on_podman_omits_load(tmp_path: Path) -> None:
    # podman build stores locally and rejects --load.
    assert "--load" not in build_test_db(tmp_path, PODMAN)
