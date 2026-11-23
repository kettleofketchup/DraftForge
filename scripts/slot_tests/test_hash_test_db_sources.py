"""hash-test-db-sources.sh hashes its own checkout, whatever the caller's cwd."""

import ast
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "hash-test-db-sources.sh"


def _other_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "other"
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "backend" / "app" / "models.py").write_text("other\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
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


def test_ignores_gitignored_runtime_dirs(tmp_path: Path) -> None:
    repo = _other_repo(tmp_path)
    (repo / ".gitignore").write_text("backend/media/\n")
    before = _hash(ROOT, str(repo))
    media = repo / "backend" / "media"
    (media / "app").mkdir(parents=True)
    (media / "app" / "models.py").write_text("junk\n")
    locked = media / "mmr_requests" / "2026" / "11"
    locked.mkdir(parents=True)
    locked.chmod(0)
    try:
        result = subprocess.run(
            [str(SCRIPT), str(repo)], capture_output=True, text=True, check=True
        )
        assert result.stderr == ""
        assert result.stdout.strip() == before
    finally:
        locked.chmod(0o755)


BACKEND = ROOT / "backend"
POPULATE_GLOBS = (
    "tests/populate.py",
    "tests/populate/*.py",
    "tests/data/*.py",
    "tests/helpers/tournament_config.py",
    "app/management/commands/populate_*.py",
)
# Imported by populate but never change the rows it writes.
NOT_DATA = {"app/cache_utils.py": "cache invalidation only"}


def _module_file(dotted: str) -> Path | None:
    base = BACKEND.joinpath(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _direct_imports(path: Path) -> set[Path]:
    package = path.relative_to(BACKEND).parent.parts
    found: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            parts = list(package[: len(package) - node.level + 1]) if node.level else []
            module = ".".join([*parts, *([node.module] if node.module else [])])
            targets = []
            for alias in node.names:
                sub = _module_file(f"{module}.{alias.name}")
                targets.append(f"{module}.{alias.name}" if sub else module)
        else:
            continue
        for target in targets:
            if (file := _module_file(target)) is not None:
                found.add(file)
    return found


def test_hashes_every_backend_module_populate_imports() -> None:
    listed = set(_list(ROOT))
    seeds = {p for pattern in POPULATE_GLOBS for p in BACKEND.glob(pattern)}
    imported = {
        str(f.relative_to(ROOT)) for seed in seeds for f in _direct_imports(seed)
    }
    missing = sorted(
        f for f in imported - listed if f.removeprefix("backend/") not in NOT_DATA
    )
    assert missing == []


def test_hashes_the_signup_write_path() -> None:
    listed = set(_list(ROOT))
    assert {"backend/events/services.py", "backend/events/ledger.py"} <= listed


def _list(cwd: Path) -> list[str]:
    return _hash(cwd, "--list").splitlines()


def _workflow_paths() -> list[str]:
    text = (ROOT / ".github" / "workflows" / "build-test-db.yml").read_text()
    block = text.split("paths:", 1)[1].split("workflow_dispatch:", 1)[0]
    return re.findall(r"- '([^']+)'", block)


def _glob_regex(pattern: str) -> re.Pattern[str]:
    out = re.escape(pattern).replace(r"\*\*", "\0").replace(r"\*", "[^/]*")
    return re.compile(out.replace("\0", ".*") + r"\Z")


def test_build_workflow_triggers_on_every_hashed_file() -> None:
    patterns = [_glob_regex(p) for p in _workflow_paths()]
    unmatched = [f for f in _list(ROOT) if not any(p.match(f) for p in patterns)]
    assert unmatched == []
