import socket
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.slots import DF_PROJECT_RE, REAL_HOST, parse_ps_output, port_busy

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_ps_fixture() -> None:
    owners = parse_ps_output((FIXTURES / "ps_podman_6_1_4.txt").read_text())
    by_name = {o.name: o for o in owners}
    assert len(owners) == 4
    normal = by_name["redis"]
    assert normal.oneoff is False and normal.project == "df" and normal.running is True
    assert normal.service == "redis"
    assert normal.config_files[0].endswith("docker-compose.test.yaml")
    oneoff = by_name["df-backend-run-3f2a9c1d07e4"]
    assert oneoff.oneoff is True and oneoff.running is False
    assert len(oneoff.config_files) == 2
    plain = by_name["cliproxyapi"]
    assert plain.project == "" and plain.working_dir is None and plain.config_files == ()
    assert by_name["df-s2-nginx-1"].working_dir == Path("/tmp/my wt")


def test_parse_ps_treats_no_value_as_empty() -> None:
    (o,) = parse_ps_output("x\trunning\t<no value>\t<no value>\t<no value>\t<no value>\t<no value>\n")
    assert o.project == "" and o.working_dir is None and o.config_files == () and o.oneoff is False


def test_parse_ps_ignores_blank_lines() -> None:
    assert parse_ps_output("\n\n") == []


def test_port_busy_detects_listener() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert port_busy(s.getsockname()[1]) is True
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert port_busy(free) is False


GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def test_live_worktrees_lists_resolved_paths(tmp_path: Path) -> None:
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    subprocess.run(["git", "-C", str(main), *GIT_ID, "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "b"], check=True)
    assert REAL_HOST.live_worktrees(main) == {main.resolve(), (tmp_path / "wt").resolve()}


def test_real_run_merges_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DF_KEEP_ME", "kept")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "df")
    rc, out = REAL_HOST.run(
        [sys.executable, "-c", "import os; print(os.environ['DF_KEEP_ME'], os.environ['COMPOSE_PROJECT_NAME'])"],
        {"COMPOSE_PROJECT_NAME": "df-s4"},
        True,
    )
    assert (rc, out.strip()) == (0, "kept df-s4")


@pytest.mark.parametrize(
    "project,ok",
    [("df", True), ("df-dev", True), ("df-s3", True), ("df-run-0a1b2c3d", True),
     ("df-s10", False), ("dfx", False), ("df-run-XYZ", False), ("cliproxyapi", False), ("", False)],
)
def test_df_project_pattern(project: str, ok: bool) -> None:
    assert bool(DF_PROJECT_RE.match(project)) is ok
