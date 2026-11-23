"""Run docker::buildx against a recording docker stub that reports Docker or podman."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.slot_tests._docker_stub import DOCKER, PODMAN, calls, docker_stub

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


def run_build(
    tmp_path: Path, version: str, *flags: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    assert JUST is not None
    log = tmp_path / "argv"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "docker"
    stub.write_text(DOCKER_STUB.format(version=version, log=log))
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("DF_ZOT_REGISTRY", None)
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "docker::nginx::build", *flags],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return result, log


def build(tmp_path: Path, version: str, *flags: str) -> list[str]:
    result, log = run_build(tmp_path, version, *flags)
    assert result.returncode == 0, result.stderr
    return log.read_bytes().decode().split("\0")[:-1]


def nginx_hash() -> str:
    return subprocess.run(
        [str(ROOT / "scripts/hash-docker-image.sh"), "nginx"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]


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


def test_no_cache_drops_cache_from_and_to(tmp_path: Path) -> None:
    # A release must neither read nor overwrite the :buildcache main and previews read.
    argv = build(tmp_path, DOCKER, "--push", "--no-cache")
    assert "--no-cache" in argv
    assert "--push" in argv
    assert "--cache-from" not in argv
    assert "--cache-to" not in argv


def test_release_push_passes_no_cache() -> None:
    assert JUST is not None
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "--show", "docker::release::push"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--no-cache" in result.stdout


@pytest.mark.parametrize("flags", [(), ("--push",)])
def test_podman_build_skips_registry_cache(
    tmp_path: Path, flags: tuple[str, ...]
) -> None:
    argv = build(tmp_path, PODMAN, *flags)
    assert argv[:2] == ["buildx", "build"]
    assert "--cache-from" not in argv
    assert "--cache-to" not in argv
    assert "--provenance=false" not in argv
    assert argv[-1] == "nginx"


CI_IMAGE = "ghcr.io/kettleofketchup/draftforge-ci/nginx"
ZOT_CACHE = "zot.zot.svc.cluster.local:5000/buildcache/pr/draftforge/nginx"


def test_trusted_mode_is_todays_build_plus_platform(tmp_path: Path) -> None:
    h = nginx_hash()
    argv = build(tmp_path, DOCKER)
    assert values(argv, "--platform") == ["linux/amd64"]
    assert "--provenance=false" in argv
    assert values(argv, "--tag") == [f"{IMAGE}:latest", f"{IMAGE}:{h}"]
    assert values(argv, "--cache-from") == [f"type=registry,ref={IMAGE}:buildcache"]
    assert "--load" in argv
    assert "--push" not in argv
    pushed = build(tmp_path, DOCKER, "--mode=trusted", "--push")
    assert values(pushed, "--cache-to") == [
        f"type=registry,ref={IMAGE}:buildcache,mode=max"
    ]
    assert "--push" in pushed
    assert "--load" not in pushed


def test_pr_mode_tags_only_the_ci_image(tmp_path: Path) -> None:
    h = nginx_hash()
    argv = build(tmp_path, DOCKER, "--mode=pr", "--pr=42")
    tags = values(argv, "--tag")
    assert tags == [f"{CI_IMAGE}:pr-42-{h}"]
    assert not any("/draftforge/nginx:latest" in a for a in argv)
    assert not any(t.startswith("ghcr.io/kettleofketchup/draftforge/") for t in tags)
    assert values(argv, "--platform") == ["linux/amd64"]
    assert "--provenance=false" in argv
    assert "--push" in argv
    assert "--load" not in argv


def test_pr_mode_cache_refs(tmp_path: Path) -> None:
    argv = build(tmp_path, DOCKER, "--mode=pr", "--pr=42")
    assert values(argv, "--cache-from") == [
        f"type=registry,ref={ZOT_CACHE}:pr-42",
        f"type=registry,ref={IMAGE}:buildcache",
    ]
    cache_to = values(argv, "--cache-to")
    assert cache_to == [
        f"type=registry,ref={ZOT_CACHE}:pr-42,mode=max,image-manifest=true,"
        "oci-mediatypes=true,ignore-error=true"
    ]
    assert not any("ghcr.io" in c for c in cache_to)


def assert_rejected(tmp_path: Path, *flags: str) -> None:
    result, log = run_build(tmp_path, DOCKER, *flags)
    assert result.returncode == 2, result.stderr
    assert not log.exists()


def test_pr_mode_requires_a_pr_number(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--mode=pr")


def test_pr_mode_rejects_release(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--mode=pr", "--pr=1", "--release")


def test_pr_number_must_be_numeric(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--mode=pr", "--pr=abc")


def test_unknown_mode_exits_2(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--mode=nightly")


def test_pr_mode_rejects_no_cache(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--mode=pr", "--pr=1", "--no-cache")


def test_pr_number_needs_pr_mode(tmp_path: Path) -> None:
    assert_rejected(tmp_path, "--pr=5")


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


def populate_stub_env(tmp_path: Path, env: dict[str, str]) -> dict[str, str]:
    """Stub out db::populate::fresh: a no-op python and temp DB paths."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    python = bin_dir / "python"
    python.write_text("#!/usr/bin/env bash\n")
    python.chmod(0o755)
    db_dir = tmp_path / "dbs"
    db_dir.mkdir()
    return {
        **env,
        "DF_JUST_PYTHON": str(python),
        "DF_TEST_DB_FILE": str(tmp_path / "test.db.sqlite3"),
        "DF_DB_DIR": str(db_dir),
    }


def run_test_db_build(
    env: dict[str, str], *flags: str
) -> subprocess.CompletedProcess[str]:
    assert JUST is not None
    return subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "docker::db::build", *flags],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def build_test_db(tmp_path: Path, version: str) -> list[str]:
    log = tmp_path / "argv"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(TEST_DB_DOCKER_STUB.format(version=version, log=log))
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = run_test_db_build(populate_stub_env(tmp_path, env))
    assert result.returncode == 0, result.stderr
    return log.read_bytes().decode().split("\0")[:-1]


def test_test_db_build_loads_the_image_into_docker(tmp_path: Path) -> None:
    # A docker-container buildx builder keeps the result in its cache without --load.
    assert "--load" in build_test_db(tmp_path, DOCKER)


def test_test_db_build_on_podman_omits_load(tmp_path: Path) -> None:
    # podman build stores locally and rejects --load.
    assert "--load" not in build_test_db(tmp_path, PODMAN)


RUNNER = "ghcr.io/kettleofketchup/draftforge/playwright-runner"


def _recorded_just(
    tmp_path: Path, recipe: str, *args: str, **extra: str
) -> list[list[str]]:
    """Run a recipe with a docker stub that logs every call, one argv per line."""
    assert JUST is not None
    log = tmp_path / "calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(
        '#!/usr/bin/env bash\n[[ "${1-}" == "--version" ]] && '
        f'{{ echo "{DOCKER}"; exit 0; }}\n'
        f'echo "$*" >> {log}\n'
    )
    stub.chmod(0o755)
    env = {
        **{k: v for k, v in os.environ.items() if k != "DF_PW_CONTAINER"},
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        **extra,
    }
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), recipe, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [line.split() for line in log.read_text().splitlines()]


def _hash(service: str) -> str:
    return subprocess.run(
        [str(ROOT / "scripts" / "hash-docker-image.sh"), service],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def db_content_hash() -> str:
    return subprocess.run(
        [str(ROOT / "scripts/hash-test-db-sources.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_runner_build_uses_its_own_dockerfile_and_hash(tmp_path: Path) -> None:
    (argv,) = _recorded_just(tmp_path, "docker::frontend::build-pw")
    assert argv[:2] == ["buildx", "build"]
    assert argv[argv.index("--file") + 1] == "frontend/Dockerfile.playwright"
    assert argv[argv.index("--target") + 1] == "runner"
    tags = {argv[i + 1] for i, a in enumerate(argv) if a == "--tag"}
    assert tags == {f"{RUNNER}:latest", f"{RUNNER}:{_hash('playwright')}"}
    assert argv[-1] == "frontend"


def test_runner_dockerfile_matches_the_playwright_version() -> None:
    package = (ROOT / "frontend" / "package.json").read_text()
    version = package.split('"@playwright/test": "')[1].split('"')[0]
    dockerfile = (ROOT / "frontend" / "Dockerfile.playwright").read_text()
    assert f"FROM mcr.microsoft.com/playwright:v{version}-noble AS runner" in dockerfile
    assert "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH" not in dockerfile


def _pulled(calls: list[list[str]]) -> set[str]:
    return {c[-1].rsplit(":", 1)[0] for c in calls if c[0] == "pull"}


def test_all_pull_skips_the_runner_by_default(tmp_path: Path) -> None:
    assert RUNNER not in _pulled(_recorded_just(tmp_path, "docker::all-pull"))


def test_all_pull_includes_the_runner_for_container_playwright(
    tmp_path: Path,
) -> None:
    calls = _recorded_just(tmp_path, "docker::all-pull", DF_PW_CONTAINER="1")
    assert f"pull -q {RUNNER}:{_hash('playwright')}".split() in calls
    assert f"tag {RUNNER}:{_hash('playwright')} {RUNNER}:latest".split() in calls


def test_all_push_pushes_the_runner(tmp_path: Path) -> None:
    calls = _recorded_just(tmp_path, "docker::all-push")
    runner = [c for c in calls if f"{RUNNER}:latest" in c]
    assert len(runner) == 1 and "--push" in runner[0]


def test_hash_only_push_drops_latest_and_cache_export(tmp_path: Path) -> None:
    (argv,) = _recorded_just(
        tmp_path, "docker::frontend::build-pw", "--push", "--hash-only"
    )
    tags = {argv[i + 1] for i, a in enumerate(argv) if a == "--tag"}
    assert tags == {f"{RUNNER}:{_hash('playwright')}"}
    assert "--cache-to" not in argv
    assert "--cache-from" in argv
    assert "--push" in argv


def test_test_db_push_hash_only_skips_latest(tmp_path: Path) -> None:
    db_hash = subprocess.run(
        [str(ROOT / "scripts" / "hash-test-db-sources.sh")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    registry = "ghcr.io/kettleofketchup/draftforge/test-db"
    calls = _recorded_just(tmp_path, "docker::db::push", "--hash-only")
    assert [c[1] for c in calls if c[0] == "push"] == [f"{registry}:{db_hash}"]


def test_test_db_pr_mode_pushes_through_buildx(tmp_path: Path) -> None:
    # The home runner has no daemon: everything goes through the remote buildx builder.
    env, log = docker_stub(tmp_path)
    result = run_test_db_build(populate_stub_env(tmp_path, env), "--mode=pr", "--pr=42")
    assert result.returncode == 0, result.stderr
    recorded = calls(log)
    builds = [c for c in recorded if c[:2] == ["buildx", "build"]]
    assert len(builds) == 1
    argv = builds[0]
    tag = f"ghcr.io/kettleofketchup/draftforge-ci/test-db:pr-42-{db_content_hash()}"
    assert values(argv, "--tag") == [tag]
    assert values(argv, "--platform") == ["linux/amd64"]
    assert "--provenance=false" in argv
    assert values(argv, "--build-arg") == [f"CONTENT_HASH={db_content_hash()}"]
    assert "--push" in argv
    assert "--load" not in argv
    assert not any(c[:1] in (["image"], ["tag"], ["push"], ["build"]) for c in recorded)


@pytest.mark.parametrize(
    "flags",
    [("--mode=pr",), ("--mode=pr", "--pr=abc"), ("--pr=5",), ("--mode=nightly",)],
)
def test_test_db_pr_mode_requires_pr(tmp_path: Path, flags: tuple[str, ...]) -> None:
    env, log = docker_stub(tmp_path)
    result = run_test_db_build(populate_stub_env(tmp_path, env), *flags)
    assert result.returncode == 2, result.stderr
    assert calls(log) == []
