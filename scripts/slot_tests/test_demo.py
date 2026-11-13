import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import scripts.demo as demo


class FakePlaywright:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.argvs: list[list[str]] = []

    def __call__(
        self, argv: Sequence[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.argvs.append(list(argv))
        return subprocess.CompletedProcess(list(argv), self.returncode)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    log: list[str] = []
    monkeypatch.setattr(demo, "flush_test_redis", lambda: None)
    monkeypatch.setattr(demo, "playwright_env", lambda: {})
    monkeypatch.setattr(demo, "reset_demo_data", lambda key: log.append(f"reset:{key}"))
    monkeypatch.setattr(demo, "copy_demo_videos", lambda: log.append("copy_videos"))
    monkeypatch.setattr(
        demo, "copy_demo_snapshots", lambda: log.append("copy_snapshots")
    )
    monkeypatch.setattr(demo, "DEMO_RESULTS", tmp_path / "demo-results")
    return log


def _playwright(monkeypatch: pytest.MonkeyPatch, returncode: int) -> FakePlaywright:
    fake = FakePlaywright(returncode)
    monkeypatch.setattr(demo.subprocess, "run", fake)
    return fake


@pytest.mark.parametrize(
    "argv",
    [
        ["shuffle"],
        ["snake"],
        ["herodraft"],
        ["csv"],
        ["event-creation"],
        ["roll-call"],
        ["create"],
        ["create", "--spec", "snake"],
        ["all"],
        ["snapshots"],
    ],
)
def test_failed_demo_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, calls: list[str], argv: list[str]
) -> None:
    _playwright(monkeypatch, 1)
    assert demo.main(argv) != 0


@pytest.mark.parametrize(
    "argv",
    [["shuffle"], ["roll-call"], ["create"], ["all"], ["snapshots"]],
)
def test_successful_demo_exits_zero(
    monkeypatch: pytest.MonkeyPatch, calls: list[str], argv: list[str]
) -> None:
    _playwright(monkeypatch, 0)
    assert demo.main(argv) == 0


def test_failed_demo_still_copies_partial_videos(
    monkeypatch: pytest.MonkeyPatch, calls: list[str]
) -> None:
    _playwright(monkeypatch, 1)
    assert demo.main(["roll-call"]) == 1
    assert calls[-1] == "copy_videos"


def test_failed_demo_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _playwright(monkeypatch, 1)
    demo.main(["shuffle"])
    assert "playwright exited 1" in capsys.readouterr().err


def test_record_all_runs_every_demo_in_one_pass(
    monkeypatch: pytest.MonkeyPatch, calls: list[str]
) -> None:
    fake = _playwright(monkeypatch, 1)
    assert demo.main(["all"]) != 0
    assert len(fake.argvs) == 1
    assert "--grep" not in fake.argvs[0]
    assert calls[-1] == "copy_videos"


def test_quick_keeps_post_processing_after_failed_recording(
    monkeypatch: pytest.MonkeyPatch, calls: list[str]
) -> None:
    _playwright(monkeypatch, 1)
    monkeypatch.setattr(demo, "trim", lambda: calls.append("trim") or 0)
    monkeypatch.setattr(demo, "gifs", lambda **_: calls.append("gifs") or 0)
    assert demo.main(["quick"]) != 0
    assert calls[-2:] == ["trim", "gifs"]


@pytest.mark.parametrize(
    ("trimmed", "converted", "expected"),
    [(0, 0, 0), (1, 0, 1), (0, 1, 1)],
)
def test_quick_after_successful_recording(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    trimmed: int,
    converted: int,
    expected: int,
) -> None:
    _playwright(monkeypatch, 0)
    monkeypatch.setattr(demo, "trim", lambda: trimmed)
    monkeypatch.setattr(demo, "gifs", lambda **_: converted)
    assert demo.main(["quick"]) == expected
