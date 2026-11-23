import fcntl
import os
import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import scripts.slots as slots
from scripts.slot_tests._helpers import FakeHost, owner
from scripts.slots import (
    RUN_GRACE_S,
    SlotError,
    reap_project,
    reap_run_orphans,
    run_one_off,
    status_report,
)

MakeWt = Callable[[str], Path]
NOW = 1_000_000.0
RUN = "df-run-e792e383"
RUN_FILES = (
    "/w/docker/docker-compose.test.yaml",
    "/w/docker/docker-compose.slot.yaml",
    "/w/docker/docker-compose.slot-offline.yaml",
    "/w/docker/docker-compose.run.yaml",
)


def _down(project: str) -> list[str]:
    return ["docker", "compose", "-p", project, "down", "-v", "--remove-orphans"]


def _lock(h: FakeHost, project: str) -> Path:
    return h.common / "df-runs" / f"{project}.lock"


@contextmanager
def _held(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _redis(project: str, wd: Path) -> slots.ContainerOwner:
    return owner(
        name=f"redis-run-{project[-8:]}",
        project=project,
        service="redis",
        wd=wd,
        config_files=RUN_FILES,
    )


def _oneoff(project: str, wd: Path, *, running: bool = True) -> slots.ContainerOwner:
    return owner(
        name=f"{project}-backend-run-1a2b",
        project=project,
        service="backend",
        wd=wd,
        running=running,
        oneoff=True,
        config_files=RUN_FILES,
    )


def test_reap_run_refuses_while_oneoff_runs(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects[RUN] = [_redis(RUN, other), _oneoff(RUN, other)]
    fake_host.container_active[RUN] = NOW - 5 * 3600
    with pytest.raises(SlotError, match="in progress") as exc:
        reap_project(RUN, me, fake_host)
    assert "test::down" not in str(exc.value)
    assert f"{RUN}-backend-run-1a2b" in str(exc.value)
    assert fake_host.compose_calls == []


def test_reap_run_refuses_while_creator_holds_lock(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects[RUN] = [_redis(RUN, other)]
    fake_host.container_active[RUN] = NOW - 5 * 3600
    with _held(_lock(fake_host, RUN)):
        with pytest.raises(SlotError, match="still running") as exc:
            reap_project(RUN, me, fake_host)
    assert "test::down" not in str(exc.value)
    assert fake_host.compose_calls == []


def test_reap_run_with_released_lock_reaps_at_once(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects[RUN] = [_redis(RUN, other), _oneoff(RUN, other, running=False)]
    fake_host.container_active[RUN] = NOW - 60
    with _held(_lock(fake_host, RUN)):
        pass
    reap_project(RUN, me, fake_host)
    assert fake_host.compose_calls == [_down(RUN)]
    assert not _lock(fake_host, RUN).exists()


def test_reap_run_without_lock_waits_out_grace(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    fake_host.projects[RUN] = [_redis(RUN, other)]
    fake_host.container_active[RUN] = NOW - RUN_GRACE_S + 60
    with pytest.raises(SlotError, match="started") as exc:
        reap_project(RUN, me, fake_host)
    assert "test::down" not in str(exc.value)
    assert fake_host.compose_calls == []
    fake_host.container_active[RUN] = NOW - RUN_GRACE_S - 60
    reap_project(RUN, me, fake_host)
    assert fake_host.compose_calls == [_down(RUN)]


def test_reap_run_without_lock_and_unknown_activity_refuses(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me = make_worktree("me")
    fake_host.projects[RUN] = [_redis(RUN, me)]
    with pytest.raises(SlotError, match="refusing to reap"):
        reap_project(RUN, me, fake_host)
    assert fake_host.compose_calls == []


def test_reap_slot_project_still_points_at_test_down(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, live = make_worktree("me"), make_worktree("live")
    fake_host.projects["df-s3"] = [owner(project="df-s3", wd=live)]
    with pytest.raises(SlotError, match="just test::down"):
        reap_project("df-s3", me, fake_host)


def test_sweep_reaps_only_orphaned_run_projects(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    me, other = make_worktree("me"), make_worktree("other")
    old = NOW - 2 * RUN_GRACE_S
    orphan, busy, locked, young = (
        "df-run-0000000a",
        "df-run-0000000b",
        "df-run-0000000c",
        "df-run-0000000d",
    )
    gone, foreign = "df-run-0000000e", "df-run-0000000f"
    fake_host.projects = {
        orphan: [_redis(orphan, other)],
        busy: [_redis(busy, other), _oneoff(busy, other)],
        locked: [_redis(locked, me)],
        young: [_redis(young, other)],
        gone: [_redis(gone, tmp_path / "removed-worktree")],
        foreign: [
            owner(project=foreign, wd=other, config_files=("/w/docker/other.yaml",))
        ],
        "df-s3": [owner(project="df-s3", wd=tmp_path / "removed-worktree")],
    }
    fake_host.container_active = {p: old for p in fake_host.projects}
    fake_host.container_active[young] = NOW - 60
    with _held(_lock(fake_host, locked)):
        reaped = reap_run_orphans(me, fake_host)
    assert reaped == [orphan, gone]
    assert fake_host.compose_calls == [_down(orphan), _down(gone)]


def test_sweep_survives_docker_failure(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    me = make_worktree("me")
    fake_host.projects[RUN] = [_redis(RUN, me)]

    def boom(project: str) -> float | None:
        raise SlotError("docker inspect failed (1)")

    fake_host.container_activity = boom  # type: ignore[method-assign]
    assert reap_run_orphans(me, fake_host) == []
    assert fake_host.compose_calls == []
    assert "docker inspect failed" in capsys.readouterr().err


def test_cli_reap_stale_sweeps_run_orphans(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, other = make_worktree("a"), make_worktree("other")
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(slots, "_toplevel", lambda cwd: root)
    fake_host.projects[RUN] = [_redis(RUN, other)]
    fake_host.container_active[RUN] = NOW - 2 * RUN_GRACE_S
    assert slots.main(["--root", str(root), "reap", "--stale"]) == 0
    err = capsys.readouterr().err
    assert f"reaped orphaned test::run project {RUN}" in err
    assert fake_host.compose_calls == [_down(RUN)]


def test_status_labels_run_projects(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    me = make_worktree("me")
    busy, orphan = "df-run-0000000b", "df-run-0000000a"
    fake_host.projects = {
        busy: [_redis(busy, me), _oneoff(busy, me)],
        orphan: [_redis(orphan, me)],
    }
    fake_host.container_active = {p: NOW - 2 * RUN_GRACE_S for p in fake_host.projects}
    out = status_report(me, fake_host)
    lines = {ln.split()[1]: ln for ln in out.splitlines() if ln.startswith("project ")}
    assert "test::run in progress" in lines[busy] and "slot-reap" not in lines[busy]
    assert f"just test::slot-reap {orphan}" in lines[orphan]
    assert "owner live" not in lines[orphan]
    assert fake_host.compose_calls == []


def test_ephemeral_run_holds_lock_and_removes_it(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt = make_worktree("a")
    held: list[bool] = []

    def run(argv: list[str], env: dict[str, str], capture: bool) -> tuple[int, str]:
        fake_host.compose_calls.append(argv)
        if "run" in argv:
            (lock,) = (fake_host.common / "df-runs").iterdir()
            held.append(slots.run_lock_state(lock) == "held")
        return 0, ""

    monkeypatch.setattr(fake_host, "run", run)
    assert run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host) == 0
    assert held == [True]
    assert list((fake_host.common / "df-runs").iterdir()) == []


def test_ephemeral_run_keeps_free_lock_when_down_fails(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    fake_host.run_outputs = [(0, ""), (1, "")]
    run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host)
    (lock,) = (fake_host.common / "df-runs").iterdir()
    assert slots.run_lock_state(lock) == "free"
    project = fake_host.compose_calls[0][fake_host.compose_calls[0].index("-p") + 1]
    assert lock.name == f"{project}.lock"


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_ephemeral_run_cleans_up_on_signal(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    sig: signal.Signals,
) -> None:
    wt = make_worktree("a")
    before = signal.getsignal(sig)

    def run(argv: list[str], env: dict[str, str], capture: bool) -> tuple[int, str]:
        fake_host.compose_calls.append(argv)
        if "run" in argv:
            os.kill(os.getpid(), sig)
        return 0, ""

    monkeypatch.setattr(fake_host, "run", run)
    with pytest.raises(SystemExit) as exc:
        run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host)
    assert exc.value.code == 128 + sig
    assert fake_host.compose_calls[-1][-3:] == ["down", "-v", "--remove-orphans"]
    assert signal.getsignal(sig) == before


def test_ephemeral_run_sweeps_orphans_first(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("other")
    fake_host.projects[RUN] = [_redis(RUN, other)]
    fake_host.container_active[RUN] = NOW - 2 * RUN_GRACE_S
    run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host)
    assert fake_host.compose_calls[0] == _down(RUN)
    assert "run" in fake_host.compose_calls[1]
