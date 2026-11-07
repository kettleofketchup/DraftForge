import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ["tasks.py", "scripts/tests.py", "scripts/docker.py", "scripts/update.py"]


def test_no_docker_stop_all() -> None:
    for rel in SCANNED:
        text = (ROOT / rel).read_text()
        assert "docker_stop_all" not in text, rel
        assert "docker ps -aq" not in text, rel


RAW_COMPOSE = re.compile(r"docker compose(?![^\n]*scripts\.slots)")
RAW_COMPOSE_SCANNED = [
    "tasks.py",
    "scripts/tests.py",
    "scripts/docker.py",
    "scripts/update.py",
    "just/test/pw.just",
    "just/test/mod.just",
    "just/dev.just",
]


def test_no_raw_compose_outside_helper() -> None:
    for rel in RAW_COMPOSE_SCANNED:
        hits = [
            line
            for line in (ROOT / rel).read_text().splitlines()
            if RAW_COMPOSE.search(line) and "-p ." not in line
        ]
        assert hits == [], (rel, hits)


def test_no_localhost_literal_in_scripts_tests() -> None:
    assert "https://localhost" not in (ROOT / "scripts/tests.py").read_text()


def test_no_docker_host_in_scripts() -> None:
    for rel in ["scripts/tests.py", "scripts/compose.py"]:
        assert "DOCKER_HOST" not in (ROOT / rel).read_text(), rel
