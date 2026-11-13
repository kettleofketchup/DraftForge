import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import scripts.compose
import scripts.slots as slots
from scripts.compose import flush_test_redis, main, playwright_env
from scripts.slot_tests._helpers import FakeHost
from scripts.slots import NoSlotFile, SlotError


def _ci(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_TEMP": "/tmp/r",
        "GITHUB_WORKSPACE": "/tmp/w",
    }.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def slotless(
    monkeypatch: pytest.MonkeyPatch,
    fake_host: FakeHost,
    make_worktree: Callable[[str], Path],
) -> tuple[Path, FakeHost]:
    root = make_worktree("a")
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    return root, fake_host


class RecordedRun:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []
        self.kws: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        self.argvs.append(list(argv))
        self.kws.append(kw)
        return subprocess.CompletedProcess(argv, 0)

    @property
    def cmds(self) -> list[str]:
        return [shlex.join(a) for a in self.argvs]


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> RecordedRun:
    rec = RecordedRun()
    monkeypatch.setattr(scripts.compose.subprocess, "run", rec)
    return rec


def test_playwright_env_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    _ci(monkeypatch)
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    assert playwright_env() == {
        "DF_BASE_URL": "https://localhost",
        "DF_BASE_URL_SOURCE": "runner",
    }


def test_playwright_env_local_slot(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    assert playwright_env() == {
        "DF_BASE_URL": "https://s3.localhost:13443",
        "DF_BASE_URL_SOURCE": "runner",
    }


def test_playwright_env_local_without_slot_refuses(
    slotless: tuple[Path, FakeHost],
) -> None:
    with pytest.raises(NoSlotFile):
        playwright_env()


def test_playwright_env_container(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripts.compose, "in_container", lambda: True)
    assert playwright_env() == {
        "DF_BASE_URL": "https://nginx",
        "DF_BASE_URL_SOURCE": "container",
    }
    assert slotless[1].calls == []


def test_env_cli_prints_shell_quoted_exports(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    assert main(["env"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "export DF_BASE_URL=https://s3.localhost:13443",
        "export DF_BASE_URL_SOURCE=runner",
    ]


def test_env_cli_without_slot_exits_1(
    slotless: tuple[Path, FakeHost], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["env"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "just test::slot" in captured.err


def test_flush_test_redis_refuses_without_slot(
    slotless: tuple[Path, FakeHost], recorded: RecordedRun
) -> None:
    with pytest.raises(SlotError, match="just test::slot"):
        flush_test_redis()
    assert recorded.argvs == []


def test_flush_test_redis_uses_fixture_slot(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    recorded: RecordedRun,
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    flush_test_redis()
    assert " -p df-s3 " in recorded.cmds[0]
    assert recorded.cmds[0].endswith("exec -T redis redis-cli FLUSHALL")
    env = recorded.kws[0]["env"]
    assert isinstance(env, dict) and env["COMPOSE_PROJECT_NAME"] == "df-s3"


def test_flush_test_redis_ci_argv(
    monkeypatch: pytest.MonkeyPatch, recorded: RecordedRun
) -> None:
    _ci(monkeypatch)
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    flush_test_redis()
    assert " -p df " in recorded.cmds[0]
    assert "docker-compose.ci.override.yaml" in recorded.cmds[0]
    assert recorded.cmds[0].endswith("exec -T redis redis-cli FLUSHALL")


def test_flush_test_redis_is_fatal(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    recorded: RecordedRun,
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    flush_test_redis()
    assert recorded.kws[0]["check"] is True


def test_flush_cli_reports_compose_failure(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()

    def fail(argv: list[str], **_: object) -> None:
        raise subprocess.CalledProcessError(4, argv)

    monkeypatch.setattr(scripts.compose.subprocess, "run", fail)
    assert main(["flush-redis"]) == 4
    assert "FLUSHALL failed (exit 4)" in capsys.readouterr().err


@pytest.mark.parametrize("marker", [".dockerenv", "run/.containerenv"])
def test_in_container_detects_docker_and_podman(tmp_path: Path, marker: str) -> None:
    (tmp_path / marker).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / marker).touch()
    assert scripts.compose.in_container(tmp_path)


def test_in_container_false_on_bare_host(tmp_path: Path) -> None:
    (tmp_path / "proc/1").mkdir(parents=True)
    (tmp_path / "proc/1/cgroup").write_text("0::/init.scope\n")
    assert not scripts.compose.in_container(tmp_path)


class FakeSock:
    def __init__(self, reply: bytes) -> None:
        self.sent = b""
        self.reply = reply

    def __enter__(self) -> "FakeSock":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, _: int) -> bytes:
        return self.reply


def test_flush_test_redis_in_container_skips_slot_and_compose(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    recorded: RecordedRun,
) -> None:
    sock = FakeSock(b"+OK\r\n")
    addrs: list[tuple[str, int]] = []

    def connect(addr: tuple[str, int], timeout: float) -> FakeSock:
        addrs.append(addr)
        return sock

    monkeypatch.setattr(scripts.compose, "in_container", lambda: True)
    monkeypatch.setattr(scripts.compose.socket, "create_connection", connect)
    flush_test_redis()
    assert recorded.argvs == [] and slotless[1].calls == []
    assert addrs == [("redis", 6379)] and b"FLUSHALL" in sock.sent


def test_flush_test_redis_in_container_unreachable_warns(
    slotless: tuple[Path, FakeHost],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(addr: tuple[str, int], timeout: float) -> FakeSock:
        raise OSError("connection refused")

    monkeypatch.setattr(scripts.compose, "in_container", lambda: True)
    monkeypatch.setattr(scripts.compose.socket, "create_connection", refuse)
    flush_test_redis()
    assert "connection refused" in capsys.readouterr().err
