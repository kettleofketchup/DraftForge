"""With DF_CI_PR=<n>, test-job pulls try the PR's draftforge-ci image first.

The `prepare` job on the home runner pushes what it builds only as
draftforge-ci/<img>:pr-<n>-<hash>; test jobs then set DF_CI_PR and retag that image
as the draftforge/ name compose expects, falling back to main's hash tag.
"""

import subprocess
from pathlib import Path

import pytest

from scripts.slot_tests._docker_stub import JUST, ROOT, calls, docker_stub, run_just

REGISTRY = "ghcr.io/kettleofketchup/draftforge"
CI = "ghcr.io/kettleofketchup/draftforge-ci"
DB_REGISTRY = f"{REGISTRY}/test-db"
DB_IMAGE = "draftforge/test-db"
PR = "42"
STACK = {"backend-dev": "backend", "frontend-dev": "frontend", "nginx": "nginx"}

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")


def run(cmd: str, *args: str) -> str:
    return subprocess.run(
        [str(ROOT / cmd), *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def hashes() -> dict[str, str]:
    return {img: run("scripts/hash-docker-image.sh", svc) for img, svc in STACK.items()}


def stub(tmp_path: Path, existing: set[str], **extra: str) -> tuple[dict, Path]:
    env, log = docker_stub(tmp_path, existing=existing)
    for key in (
        "DF_PW_CONTAINER",
        "DF_CI_PR",
        "DF_TEST_DB_IMAGE",
        "DF_TEST_DB_REGISTRY",
    ):
        env.pop(key, None)
    env.update(extra)
    return env, log


def pulls(log: Path) -> list[str]:
    return [argv[-1] for argv in calls(log) if argv[:1] == ["pull"]]


def retags(log: Path) -> set[tuple[str, str]]:
    return {(argv[1], argv[2]) for argv in calls(log) if argv[:1] == ["tag"]}


def test_pr_image_first_and_retagged(tmp_path: Path) -> None:
    h = hashes()
    ci = {img: f"{CI}/{img}:pr-{PR}-{h[img]}" for img in STACK}
    env, log = stub(tmp_path, set(ci.values()), DF_CI_PR=PR)
    result = run_just(env, "docker::test-pull")
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(pulls(log)) == set(ci.values())
    for img, ref in ci.items():
        assert (ref, f"{REGISTRY}/{img}:{h[img]}") in retags(log)
        assert (ref, f"{REGISTRY}/{img}:latest") in retags(log)


def test_falls_back_to_mains_hash_tag(tmp_path: Path) -> None:
    h = hashes()
    ci_nginx = f"{CI}/nginx:pr-{PR}-{h['nginx']}"
    trusted = {f"{REGISTRY}/{img}:{h[img]}" for img in ("backend-dev", "frontend-dev")}
    env, log = stub(tmp_path, trusted | {ci_nginx}, DF_CI_PR=PR)
    result = run_just(env, "docker::test-pull")
    assert result.returncode == 0, result.stdout + result.stderr
    got = pulls(log)
    for img in ("backend-dev", "frontend-dev"):
        ci_ref = f"{CI}/{img}:pr-{PR}-{h[img]}"
        trusted_ref = f"{REGISTRY}/{img}:{h[img]}"
        assert got.index(ci_ref) < got.index(trusted_ref)
    assert f"{REGISTRY}/nginx:{h['nginx']}" not in got


def test_without_ci_pr_never_looks_at_draftforge_ci(tmp_path: Path) -> None:
    h = hashes()
    ci = {f"{CI}/{img}:pr-{PR}-{h[img]}" for img in STACK}
    trusted = {f"{REGISTRY}/{img}:{h[img]}" for img in STACK}
    env, log = stub(tmp_path, ci | trusted)
    result = run_just(env, "docker::test-pull")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [ref for ref in pulls(log) if ref.startswith(CI)]


def test_missing_everywhere_still_fails_for_the_in_job_rebuild(tmp_path: Path) -> None:
    env, log = stub(tmp_path, set(), DF_CI_PR=PR)
    result = run_just(env, "docker::test-pull")
    assert result.returncode != 0
    assert not retags(log)


def test_non_numeric_ci_pr_is_rejected(tmp_path: Path) -> None:
    env, log = stub(tmp_path, set(), DF_CI_PR="1 2")
    result = run_just(env, "docker::test-pull")
    assert result.returncode != 0
    assert pulls(log) == []


def test_db_pull_prefers_the_pr_test_db(tmp_path: Path) -> None:
    h = run("scripts/hash-test-db-sources.sh")
    ref = f"{CI}/test-db:pr-{PR}-{h}"
    env, log = stub(tmp_path, {ref, f"{DB_REGISTRY}:{h}"}, DF_CI_PR=PR)
    result = run_just(env, "docker::db::pull")
    assert result.returncode == 0, result.stdout + result.stderr
    assert pulls(log) == [ref]
    assert retags(log) == {(ref, f"{DB_IMAGE}:latest"), (ref, f"{DB_IMAGE}:{h}")}


def test_db_pull_falls_back_to_mains_hash_tag(tmp_path: Path) -> None:
    h = run("scripts/hash-test-db-sources.sh")
    env, log = stub(tmp_path, {f"{DB_REGISTRY}:{h}"}, DF_CI_PR=PR)
    result = run_just(env, "docker::db::pull")
    assert result.returncode == 0, result.stdout + result.stderr
    assert pulls(log) == [f"{CI}/test-db:pr-{PR}-{h}", f"{DB_REGISTRY}:{h}"]
