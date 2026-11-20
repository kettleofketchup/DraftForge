"""hash-test-db-sources.sh hashes its own checkout, whatever the caller's cwd."""

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "hash-test-db-sources.sh"


def _other_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "other"
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "backend" / "app" / "models.py").write_text("other\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _hash(cwd: Path, *args: str) -> str:
    return subprocess.run(
        [str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_hashes_its_own_checkout_from_another_repo(tmp_path: Path) -> None:
    assert _hash(_other_repo(tmp_path)) == _hash(ROOT)


def test_hashes_an_explicit_root(tmp_path: Path) -> None:
    repo = _other_repo(tmp_path)
    assert _hash(ROOT, str(repo)) == hashlib.sha256(b"other\n").hexdigest()
