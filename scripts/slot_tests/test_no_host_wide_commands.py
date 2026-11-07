from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ["tasks.py", "scripts/tests.py", "scripts/docker.py", "scripts/update.py"]


def test_no_docker_stop_all() -> None:
    for rel in SCANNED:
        text = (ROOT / rel).read_text()
        assert "docker_stop_all" not in text, rel
        assert "docker ps -aq" not in text, rel
