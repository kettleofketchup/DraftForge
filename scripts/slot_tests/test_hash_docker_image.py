"""hash-docker-image.sh hashes its own checkout, whatever the caller's cwd."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "hash-docker-image.sh"

INPUTS = {
    "frontend": ("frontend/Dockerfile", "frontend/package-lock.json"),
    "backend": ("backend/Dockerfile", "poetry.lock"),
    "nginx": (
        "nginx/Dockerfile",
        "nginx/entrypoint.sh",
        "nginx/default.template.conf",
    ),
}


def _other_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "other"
    for files in INPUTS.values():
        for rel in files:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"other {rel}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _hash(cwd: Path, *args: str) -> str:
    return subprocess.run(
        [str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize("service", INPUTS)
def test_hashes_its_own_checkout_from_another_repo(
    tmp_path: Path, service: str
) -> None:
    assert _hash(_other_repo(tmp_path), service) == _hash(ROOT, service)


@pytest.mark.parametrize("service", INPUTS)
def test_hashes_an_explicit_root(tmp_path: Path, service: str) -> None:
    repo = _other_repo(tmp_path)
    expected = hashlib.sha256(
        "".join(f"other {rel}\n" for rel in INPUTS[service]).encode()
    ).hexdigest()
    assert _hash(ROOT, service, str(repo)) == expected


def test_rejects_an_unknown_service() -> None:
    result = subprocess.run(
        [str(SCRIPT), "bogus"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Usage" in result.stderr
