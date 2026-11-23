"""docker::test-pull pulls only the images the test stack runs."""

import re
import subprocess
from pathlib import Path

import pytest

from scripts.slot_tests._docker_stub import JUST, ROOT, calls, docker_stub, run_just

REGISTRY = "ghcr.io/kettleofketchup/draftforge"

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")


def content_hash(service: str) -> str:
    return subprocess.run(
        [str(ROOT / "scripts/hash-docker-image.sh"), service],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_test_pull_pulls_only_the_stack_images(tmp_path: Path) -> None:
    stack = {
        f"{REGISTRY}/backend-dev:{content_hash('backend')}",
        f"{REGISTRY}/frontend-dev:{content_hash('frontend')}",
        f"{REGISTRY}/nginx:{content_hash('nginx')}",
    }
    env, log = docker_stub(tmp_path, existing=stack)
    env.pop("DF_PW_CONTAINER", None)
    result = run_just(env, "docker::test-pull")
    assert result.returncode == 0, result.stdout + result.stderr
    pulled = {argv[-1] for argv in calls(log) if argv[:1] == ["pull"]}
    assert pulled == stack
    assert not [
        ref for ref in pulled if re.search(r"/draftforge/(backend|frontend):", ref)
    ]


def test_test_pull_adds_the_playwright_runner_in_container_mode(tmp_path: Path) -> None:
    stack = {
        f"{REGISTRY}/backend-dev:{content_hash('backend')}",
        f"{REGISTRY}/frontend-dev:{content_hash('frontend')}",
        f"{REGISTRY}/nginx:{content_hash('nginx')}",
        f"{REGISTRY}/playwright-runner:{content_hash('playwright')}",
    }
    env, log = docker_stub(tmp_path, existing=stack)
    env["DF_PW_CONTAINER"] = "1"
    result = run_just(env, "docker::test-pull")
    assert result.returncode == 0, result.stdout + result.stderr
    pulled = {argv[-1] for argv in calls(log) if argv[:1] == ["pull"]}
    assert pulled == stack
