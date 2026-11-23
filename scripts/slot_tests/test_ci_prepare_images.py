"""ci::prepare-images builds and pushes (hash tag only) what the registry lacks."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")
REGISTRY = "ghcr.io/kettleofketchup/draftforge"

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")

DOCKER_STUB = """#!/usr/bin/env bash
echo "$*" >> {log}
case "${{1-}} ${{2-}} ${{3-}}" in
    "--version"*) echo "Docker version 27.3.1"; exit 0 ;;
    "buildx imagetools inspect") grep -qxF "$4" {present} ;;
    "buildx inspect"*) echo "Driver: docker-container" ;;
    "buildx build"*) [[ " $* " == *" --push "* ]] && {{ echo "denied: permission_denied"; exit {push_status}; }}; exit 0 ;;
    "image inspect"*) [[ -f {built} ]] ;;
    "build "*) touch {built} ;;
    "push "*) echo "denied: permission_denied"; exit {push_status} ;;
esac
"""


def _hash(*cmd: str) -> str:
    return subprocess.run(
        [str(ROOT / "scripts" / cmd[0]), *cmd[1:]],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def refs() -> dict[str, str]:
    images = {
        "frontend-dev": "frontend",
        "backend-dev": "backend",
        "playwright-runner": "playwright",
        "nginx": "nginx",
    }
    out = {
        name: f"{REGISTRY}/{name}:{_hash('hash-docker-image.sh', service)}"
        for name, service in images.items()
    }
    out["test-db"] = f"{REGISTRY}/test-db:{_hash('hash-test-db-sources.sh')}"
    return out


def prepare(
    tmp_path: Path,
    present: set[str],
    push_status: int = 0,
    *args: str,
    present_refs: frozenset[str] = frozenset(),
    **extra: str,
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    assert JUST is not None
    log = tmp_path / "calls"
    log.touch()
    present_file = tmp_path / "present"
    present_file.write_text(
        "".join(f"{ref}\n" for ref in {refs()[n] for n in present} | present_refs)
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        DOCKER_STUB.format(
            log=log,
            present=present_file,
            built=tmp_path / "built",
            push_status=push_status,
        )
    )
    python = bin_dir / "python"
    python.write_text("#!/usr/bin/env bash\n")
    for stub in (docker, python):
        stub.chmod(0o755)
    db_dir = tmp_path / "dbs"
    db_dir.mkdir()
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "GITHUB_STEP_SUMMARY",
                "DF_PREPARE_READONLY",
                "DF_PREPARE_PR",
                "RUNNER_ENVIRONMENT",
            }
        },
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "DF_JUST_PYTHON": str(python),
        "DF_TEST_DB_FILE": str(tmp_path / "test.db.sqlite3"),
        "DF_DB_DIR": str(db_dir),
        **extra,
    }
    result = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "ci::prepare-images", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result, [line.split() for line in log.read_text().splitlines()]


def builds(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[:2] == ["buildx", "build"]]


def status(stdout: str, name: str) -> str:
    (row,) = [line for line in stdout.splitlines() if line.startswith(f"{name} ")]
    return row.split(None, 2)[2]


ALL = {"frontend-dev", "backend-dev", "playwright-runner", "nginx", "test-db"}


def test_everything_present_builds_nothing(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL)
    assert result.returncode == 0, result.stderr
    for name in ALL:
        assert status(result.stdout, name) == "present"
    assert builds(calls) == []
    assert ["buildx", "inspect"] not in calls
    assert not any(c[0] in {"build", "push"} for c in calls)
    assert "prepare-images: done in" in result.stdout


def test_missing_image_is_built_and_pushed_by_hash_only(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL - {"playwright-runner"})
    assert result.returncode == 0, result.stderr
    (argv,) = builds(calls)
    tags = {argv[i + 1] for i, a in enumerate(argv) if a == "--tag"}
    assert tags == {refs()["playwright-runner"]}
    assert "--push" in argv
    assert "--cache-to" not in argv
    assert status(result.stdout, "playwright-runner").startswith("built+pushed in ")
    assert status(result.stdout, "nginx") == "present"
    assert "::warning::" not in result.stdout


def test_missing_test_db_is_built_and_pushed_by_hash_only(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL - {"test-db"})
    assert result.returncode == 0, result.stderr
    assert builds(calls) == []
    pushed = [c[1] for c in calls if c[0] == "push"]
    assert pushed == [refs()["test-db"]]
    assert status(result.stdout, "test-db").startswith("built+pushed in ")


def test_push_failure_warns_and_exits_zero(tmp_path: Path) -> None:
    result, _ = prepare(tmp_path, ALL - {"nginx", "test-db"}, push_status=1)
    assert result.returncode == 0, result.stderr
    assert status(result.stdout, "nginx").startswith("build or push failed")
    assert status(result.stdout, "test-db").startswith("build or push failed")
    assert "::warning::prepare: nginx test-db not pushed" in result.stdout
    assert "registry refused the push" in result.stdout


def test_readonly_reports_without_building(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL - {"backend-dev"}, DF_PREPARE_READONLY="1")
    assert result.returncode == 0, result.stderr
    assert builds(calls) == []
    assert status(result.stdout, "backend-dev").startswith("missing; not built")
    assert "::warning::prepare: backend-dev missing" in result.stdout


CI_REGISTRY = "ghcr.io/kettleofketchup/draftforge-ci"
PR = "42"


def ci_ref(name: str) -> str:
    return f"{CI_REGISTRY}/{name}:pr-{PR}-{refs()[name].rsplit(':', 1)[1]}"


def tags(argv: list[str]) -> set[str]:
    return {argv[i + 1] for i, a in enumerate(argv) if a == "--tag"}


def test_pr_mode_pushes_only_draftforge_ci_tags(tmp_path: Path) -> None:
    result, calls = prepare(
        tmp_path,
        ALL - {"frontend-dev", "nginx"},
        DF_PREPARE_PR=PR,
        RUNNER_ENVIRONMENT="self-hosted",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    built = builds(calls)
    assert {t for argv in built for t in tags(argv)} == {
        ci_ref("frontend-dev"),
        ci_ref("nginx"),
    }
    for argv in built:
        assert not any(a.startswith(f"{REGISTRY}/") for a in tags(argv))
        cache_to = [argv[i + 1] for i, a in enumerate(argv) if a == "--cache-to"]
        assert all("ghcr.io" not in c for c in cache_to), cache_to
    # The remote home BuildKit, never a local docker-container builder.
    creates = [c for c in calls if c[:2] == ["buildx", "create"]]
    assert creates and all("remote" in c for c in creates)
    assert not any("docker-container" in c for c in creates)
    assert not any(c[0] in {"build", "push", "tag"} for c in calls)
    assert status(result.stdout, "frontend-dev").startswith("built+pushed in ")
    assert f"pr-{PR}-<hash>" in result.stdout


def test_pr_mode_counts_this_prs_draftforge_ci_tag_as_present(tmp_path: Path) -> None:
    result, calls = prepare(
        tmp_path,
        ALL - {"backend-dev"},
        present_refs=frozenset({ci_ref("backend-dev")}),
        DF_PREPARE_PR=PR,
        RUNNER_ENVIRONMENT="self-hosted",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert status(result.stdout, "backend-dev") == "present"
    assert builds(calls) == []
    assert not [c for c in calls if c[:2] == ["buildx", "create"]]


def test_hosted_mode_ignores_draftforge_ci_tags(tmp_path: Path) -> None:
    # Without DF_PREPARE_PR (the hosted prepare job) only main's hash tag counts.
    result, calls = prepare(
        tmp_path,
        ALL - {"backend-dev"},
        present_refs=frozenset({ci_ref("backend-dev")}),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (argv,) = builds(calls)
    assert tags(argv) == {refs()["backend-dev"]}


def test_pr_mode_test_db_goes_through_buildx(tmp_path: Path) -> None:
    result, calls = prepare(
        tmp_path, ALL - {"test-db"}, DF_PREPARE_PR=PR, RUNNER_ENVIRONMENT="self-hosted"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (argv,) = builds(calls)
    assert tags(argv) == {ci_ref("test-db")}
    assert "--push" in argv
    assert not any(c[0] in {"build", "push", "tag"} for c in calls)
    assert status(result.stdout, "test-db").startswith("built+pushed in ")


def test_self_hosted_without_pr_mode_refuses(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL - {"nginx"}, RUNNER_ENVIRONMENT="self-hosted")
    assert result.returncode == 1
    assert "refusing to push draftforge/ tags" in result.stderr
    assert builds(calls) == []
    assert not [c for c in calls if c[:3] == ["buildx", "imagetools", "inspect"]]


def test_pr_mode_rejects_a_non_numeric_pr(tmp_path: Path) -> None:
    result, calls = prepare(tmp_path, ALL - {"nginx"}, DF_PREPARE_PR="1; true")
    assert result.returncode == 2
    assert calls == []


def test_probe_prints_missing_and_builds_nothing(tmp_path: Path) -> None:
    result, calls = prepare(
        tmp_path, ALL - {"test-db", "nginx"}, 0, "--probe", DF_PREPARE_PR=PR
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines() == ["missing=nginx test-db"]
    assert builds(calls) == []
    assert not [c for c in calls if c[:2] == ["buildx", "create"]]
