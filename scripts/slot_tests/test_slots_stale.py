import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import scripts.slots as slots
from scripts.slot_tests._helpers import FakeHost, owner, reserve
from scripts.slots import (
    SLOT_FILE_REL,
    SlotError,
    ensure_slot,
    parse_ts,
    reap_stale,
    stale_after_s,
)

MakeWt = Callable[[str], Path]
H = 3600
NOW = 1_000_000.0
DOWN_S3 = ["docker", "compose", "-p", "df-s3", "down", "-v", "--remove-orphans"]


def _reg(h: FakeHost) -> Path:
    return h.common / "df-slots"


def _sweep(h: FakeHost, root: Path) -> list[int]:
    return [a.slot for a in reap_stale(root, h)]


def test_threshold_defaults_to_12h_and_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert stale_after_s() == 12 * H
    monkeypatch.setenv("DF_SLOT_STALE_HOURS", "1.5")
    assert stale_after_s() == 1.5 * H
    for bad in ["x", "0", "-2"]:
        monkeypatch.setenv("DF_SLOT_STALE_HOURS", bad)
        with pytest.raises(SlotError, match="DF_SLOT_STALE_HOURS"):
            stale_after_s()


def test_reservation_exactly_12h_old_is_kept(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 12 * H))
    assert _sweep(fake_host, me) == []
    assert (_reg(fake_host) / "slot-3").exists()


def test_reservation_just_over_12h_is_reaped(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 12 * H - 1))
    assert _sweep(fake_host, me) == [3]
    assert not (_reg(fake_host) / "slot-3").exists()
    assert fake_host.compose_calls == []


def test_custom_threshold(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT_STALE_HOURS", "2")
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 3 * H))
    assert _sweep(fake_host, me) == [3]


def test_idle_stack_is_downed_with_scoped_project(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 13 * H))
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]
    fake_host.container_active["df-s3"] = NOW - 13 * H
    assert _sweep(fake_host, me) == [3]
    assert fake_host.compose_calls == [DOWN_S3]


def test_recently_started_container_protects_slot(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 48 * H))
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]
    fake_host.container_active["df-s3"] = NOW - 11 * H
    assert _sweep(fake_host, me) == []
    assert fake_host.compose_calls == []
    assert (_reg(fake_host) / "slot-3").exists()


def test_unreadable_container_activity_protects_slot(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 48 * H))
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]

    def boom(project: str) -> float | None:
        raise SlotError("docker inspect failed")

    monkeypatch.setattr(fake_host, "container_activity", boom)
    assert _sweep(fake_host, me) == []
    assert "docker inspect failed" in capsys.readouterr().err


def test_recent_worktree_activity_protects_slot(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 48 * H))
    fake_host.worktree_active[other] = NOW - 1 * H
    assert _sweep(fake_host, me) == []


def test_containers_with_unknown_activity_are_kept(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", 1)
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]
    assert _sweep(fake_host, me) == []
    assert fake_host.compose_calls == []


def test_container_working_dir_activity_protects_unreserved_stack(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects["df-s4"] = [owner(project="df-s4", wd=other)]
    fake_host.container_active["df-s4"] = NOW - 48 * H
    fake_host.worktree_active[other] = NOW - 60
    assert _sweep(fake_host, me) == []


def test_slot0_active_stack_is_never_reaped(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 0, other, "t", int(NOW - 48 * H))
    fake_host.projects["df"] = [owner(wd=other)]
    fake_host.container_active["df"] = NOW - 5 * H
    assert _sweep(fake_host, me) == []
    assert fake_host.compose_calls == []


def test_slot0_idle_stack_is_reaped(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 0, other, "t", int(NOW - 48 * H))
    fake_host.projects["df"] = [owner(wd=other)]
    fake_host.container_active["df"] = NOW - 13 * H
    assert _sweep(fake_host, me) == [0]
    assert fake_host.compose_calls[0][3] == "df"


def test_own_slot_and_own_containers_are_skipped(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me = make_worktree("me")
    reserve(_reg(fake_host), 2, me, "t", 1)
    fake_host.projects["df-s5"] = [owner(project="df-s5", wd=me)]
    assert _sweep(fake_host, me) == []
    assert fake_host.compose_calls == []


def test_non_test_stack_in_slot_project_is_skipped(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects["df"] = [
        owner(wd=other, config_files=("/x/docker/docker-compose.debug.yaml",))
    ]
    assert _sweep(fake_host, me) == []
    assert fake_host.compose_calls == []


def test_failed_down_keeps_reservation(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", 1)
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]
    fake_host.container_active["df-s3"] = 1
    fake_host.run_outputs.append((1, ""))
    assert _sweep(fake_host, me) == []
    assert (_reg(fake_host) / "slot-3").exists()
    assert "exited 1" in capsys.readouterr().err


def test_notice_names_slot_owner_idle_time_and_source(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 3, other, "t", int(NOW - 30 * H))
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=other)]
    fake_host.container_active["df-s3"] = NOW - 20 * H
    fake_host.worktree_active[other] = NOW - 25 * H
    _sweep(fake_host, me)
    err = capsys.readouterr().err
    assert "auto-reaped slot 3 (df-s3)" in err
    assert f"owner {other}" in err
    assert "idle 20.0h > 12h" in err
    assert "last activity: containers" in err
    assert "1 container(s) and volumes removed" in err


def test_ensure_reaps_stale_slot_before_allocating(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    me = make_worktree("me")
    for n in range(10):
        age = 13 * H if n == 6 else H
        reserve(_reg(fake_host), n, make_worktree(f"o{n}"), "t", int(NOW - age))
    env = ensure_slot(me, fake_host)
    assert env.slot == 6
    assert "auto-reaped slot 6 (df-s6)" in capsys.readouterr().err


def test_ensure_with_kept_slot_does_not_sweep(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    ensure_slot(me, fake_host)
    reserve(_reg(fake_host), 7, other, "t", 1)
    ensure_slot(me, fake_host)
    assert (_reg(fake_host) / "slot-7").exists()


def test_ensure_in_ci_does_not_sweep(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    me, other = make_worktree("me"), make_worktree("other")
    reserve(_reg(fake_host), 7, other, "t", 1)
    ensure_slot(me, fake_host)
    assert (_reg(fake_host) / "slot-7").exists()
    assert not (me / SLOT_FILE_REL).exists()


def test_cli_reap_stale(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, other = make_worktree("a"), make_worktree("other")
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(slots, "_toplevel", lambda cwd: root)
    reserve(_reg(fake_host), 3, other, "t", 1)
    reserve(_reg(fake_host), 4, other, "t", int(NOW))
    assert slots.main(["--root", str(root), "reap", "--stale"]) == 0
    err = capsys.readouterr().err
    assert "auto-reaped slot 3" in err and "slot 4" not in err
    assert slots.main(["--root", str(root), "reap", "--stale"]) == 0
    assert "no slot idle longer than 12h" in capsys.readouterr().err


def test_cli_reap_needs_exactly_one_target(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = make_worktree("a")
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(slots, "_toplevel", lambda cwd: root)
    assert slots.main(["--root", str(root), "reap"]) == 1
    assert slots.main(["--root", str(root), "reap", "--stale", "df-s3"]) == 1
    assert "either a project or --stale" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-06T22:04:14.007176174Z", 1_794_002_654.007176),
        ("2026-11-06 17:04:14.007176174 -0500 EST", 1_794_002_654.007176),
        ("2026-11-06T17:04:14.007176-05:00 some log line", 1_794_002_654.007176),
        ("2026-11-06T22:04:14Z", 1_794_002_654.0),
        ("0001-01-01 00:00:00 +0000 UTC", None),
        ("0001-01-01T00:00:00Z", None),
        ("garbage", None),
        ("", None),
    ],
)
def test_parse_ts(text: str, expected: float | None) -> None:
    got = parse_ts(text)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected, abs=1e-3)


def test_unreserved_idle_stack_is_reaped(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects["df-s4"] = [owner(project="df-s4", wd=other)]
    fake_host.container_active["df-s4"] = NOW - 13 * H
    assert [(a.slot, a.owner) for a in reap_stale(me, fake_host)] == [(4, other)]
    assert fake_host.compose_calls[0][3] == "df-s4"


def test_worktree_activity_reads_git_and_changed_files(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    for argv in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(
            ["git", "-C", str(wt), "-c", "user.email=a@b", "-c", "user.name=a", *argv],
            check=True,
        )
    gitdir = wt / ".git"
    for p in [gitdir / "index", gitdir / "HEAD", gitdir / "logs" / "HEAD"]:
        if p.exists():
            os.utime(p, (100, 100))
    (wt / "edited.py").write_text("x")
    os.utime(wt / "edited.py", (5000, 5000))
    assert slots._worktree_activity(wt) == 5000
    assert slots._worktree_activity(tmp_path / "missing") is None


def test_container_activity_uses_inspect_and_last_log_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = {
        "ps": "aaa\nbbb\n",
        "inspect": (
            "aaa\ttrue\t2026-11-06 17:04:14.0 -0500 EST\t0001-01-01 00:00:00 +0000 UTC\n"
            "bbb\tfalse\t2026-11-01T00:00:00Z\t2026-11-02T00:00:00Z\n"
        ),
        "logs": "2026-11-07T00:00:00.5Z GET /api/healthz/\n",
    }
    seen: list[list[str]] = []

    def fake_docker(args: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, outputs[args[0]], "")

    monkeypatch.setattr(slots, "_docker", fake_docker)
    assert slots._container_activity("df-s3") == pytest.approx(
        parse_ts("2026-11-07T00:00:00.5Z")
    )
    assert [a for a in seen if a[0] == "logs"] == [
        ["logs", "--timestamps", "--tail", "1", "aaa"]
    ]
    assert "label=com.docker.compose.project=df-s3" in seen[0]
