import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ["tasks.py", "scripts/tests.py", "scripts/docker.py", "scripts/update.py"]


def test_no_docker_stop_all() -> None:
    for rel in SCANNED:
        text = (ROOT / rel).read_text()
        assert "docker_stop_all" not in text, rel
        assert "docker ps -aq" not in text, rel


RAW_COMPOSE = re.compile(
    r"(?:docker[ -]compose(?![.\w-])|[\"']docker[\"'],\s*[\"']compose[\"'])"
    r"(?![^\n]*scripts\.slots)"
)
RAW_COMPOSE_EXEMPT: dict[str, str] = {
    "scripts/slots.py": "the slot-aware compose helper itself",
    "scripts/slot_tests/_helpers.py": "integration fixture probes and renders compose directly",
    "scripts/slot_tests/test_slots_allocate.py": "asserts the helper's printed down hint",
    "scripts/slot_tests/test_slots_lifecycle.py": "asserts the helper's down argv",
    "scripts/slot_tests/test_slots_stale.py": "asserts the stale reaper's down argv",
    "scripts/version.py": "version.build only builds images, never up/down/stop",
}


def _tracked_sources() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py", "*.sh", "*.just", "justfile"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return out.split()


def _raw_compose_hits(rel: str) -> list[str]:
    return [
        line
        for line in (ROOT / rel).read_text(errors="replace").splitlines()
        if RAW_COMPOSE.search(line)
    ]


def test_no_raw_compose_outside_helper() -> None:
    files = _tracked_sources()
    assert "tasks.py" in files and "justfile" in files
    hits = {
        rel: h
        for rel in files
        if rel not in RAW_COMPOSE_EXEMPT and (h := _raw_compose_hits(rel))
    }
    assert hits == {}


def test_raw_compose_exemptions_are_live() -> None:
    stale = [rel for rel in RAW_COMPOSE_EXEMPT if not _raw_compose_hits(rel)]
    assert stale == []


def test_no_localhost_literal_in_scripts_tests() -> None:
    assert "https://localhost" not in (ROOT / "scripts/tests.py").read_text()


def test_no_docker_host_in_scripts() -> None:
    for rel in ["scripts/tests.py", "scripts/compose.py"]:
        assert "DOCKER_HOST" not in (ROOT / rel).read_text(), rel
