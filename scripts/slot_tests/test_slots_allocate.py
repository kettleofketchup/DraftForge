import multiprocessing
import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

import scripts.slots
from scripts.slot_tests._helpers import FakeHost, owner, reserve
from scripts.slots import (
    SLOT_FILE_REL,
    NoSlotFile,
    SlotError,
    ensure_slot,
    lease_and_recheck,
    parse_kv,
    read_slot,
)

MakeWt = Callable[[str], Path]
DAY = 86_400


def _reg(h: FakeHost) -> Path:
    return h.common / "df-slots"


def _res(h: FakeHost, n: int) -> dict[str, str]:
    return parse_kv((_reg(h) / f"slot-{n}").read_text())


def _slot_kv(wt: Path) -> dict[str, str]:
    return parse_kv((wt / SLOT_FILE_REL).read_text())


def test_symlinked_root_is_own(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    wt = make_worktree("a")
    link = tmp_path / "link"
    link.symlink_to(wt)
    fake_host.projects["df"] = [owner(service="nginx", wd=wt)]
    fake_host.ports_busy |= {80, 443}
    via_link = ensure_slot(link, fake_host)
    assert (via_link.slot, via_link.worktree) == (0, wt)
    assert "port_busy" not in fake_host.calls
    assert ensure_slot(wt, fake_host) == via_link


def test_copied_slot_file_raises(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    shutil.copy(a / SLOT_FILE_REL, b / SLOT_FILE_REL)
    with pytest.raises(SlotError, match=re.escape(f"`.env.slot` was written for {a}")):
        read_slot(b, fake_host)


def test_oneoff_does_not_block_adoption(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [
        owner(service="nginx", wd=wt),
        owner(name="df-backend-run-1", service="backend", wd=other, oneoff=True),
    ]
    fake_host.ports_busy |= {80, 443}
    assert ensure_slot(wt, fake_host).slot == 0


def test_crash_after_reservation_readopts(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    reg = _reg(fake_host)
    reserve(reg, 4, wt, "t4", 1_000_000)
    e = ensure_slot(wt, fake_host)
    assert (e.slot, e.token) == (4, "t4")
    assert _slot_kv(wt)["DF_SLOT"] == "4"
    assert sorted(p.name for p in reg.glob("slot-*")) == ["slot-4"]


def test_read_slot_after_claim_raises(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("b")
    e = ensure_slot(wt, fake_host)
    reserve(_reg(fake_host), e.slot, other, "stolen", 1)
    with pytest.raises(
        SlotError, match=re.escape(f"slot {e.slot} now belongs to {other}")
    ):
        read_slot(wt, fake_host)
    assert (wt / SLOT_FILE_REL).exists()


def test_read_slot_without_file_raises(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    with pytest.raises(NoSlotFile, match="just test::slot"):
        read_slot(make_worktree("a"), fake_host)


def test_read_slot_without_reservation_raises(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    e = ensure_slot(wt, fake_host)
    (_reg(fake_host) / f"slot-{e.slot}").unlink()
    with pytest.raises(SlotError, match=f"no reservation for slot {e.slot}"):
        read_slot(wt, fake_host)


def fill_slots(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    slots_: range,
    t0: float,
) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for i in slots_:
        fake_host.clock_value[0] = t0 + i
        monkeypatch.setenv("DF_SLOT", str(i))
        out[i] = make_worktree(f"w{i}")
        assert ensure_slot(out[i], fake_host).slot == i
    monkeypatch.delenv("DF_SLOT")
    return out


def test_slot0_never_idle_reclaimed(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    t0 = fake_host.clock_value[0]
    a = make_worktree("a")
    assert ensure_slot(a, fake_host).slot == 0
    fill_slots(fake_host, make_worktree, monkeypatch, range(1, 10), t0)
    fake_host.clock_value[0] = t0 + 30 * DAY
    assert ensure_slot(make_worktree("new"), fake_host).slot == 1
    assert read_slot(a, fake_host).slot == 0


def test_owner_without_slot_file_is_not_stale(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    w = make_worktree("w")
    reserve(_reg(fake_host), 0, w, "t0", int(fake_host.clock_value[0]))
    assert ensure_slot(make_worktree("new"), fake_host).slot == 1
    assert "owner=" + str(w) in (_reg(fake_host) / "slot-0").read_text()


def _alloc(
    wt: str, common: str, wts: list[str], q: "multiprocessing.Queue[int]"
) -> None:
    q.put(ensure_slot(Path(wt), FakeHost(Path(common), {Path(w) for w in wts})).slot)  # type: ignore[arg-type]


def test_concurrent_allocators_get_distinct_slots(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    q: multiprocessing.Queue[int] = ctx.Queue()
    wts = [str(tmp_path.resolve() / f"w{i}") for i in range(6)]
    for w in wts:
        (Path(w) / "docker").mkdir(parents=True)
    ps = [
        ctx.Process(target=_alloc, args=(w, str(tmp_path / "git-common"), wts, q))
        for w in wts
    ]
    for p in ps:
        p.start()
    slots = [q.get(timeout=30) for _ in ps]
    for p in ps:
        p.join(timeout=30)
        assert p.exitcode == 0
    assert len(set(slots)) == 6
    assert len(list((tmp_path / "git-common" / "df-slots").glob("slot-*"))) == 6


def test_lowest_free_slot(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    assert ensure_slot(make_worktree("a"), fake_host).slot == 0


def test_stable_across_calls(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    first = ensure_slot(wt, fake_host)
    assert ensure_slot(wt, fake_host) == first


def test_valid_reservation_does_not_probe_ports(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    fake_host.calls.clear()
    ensure_slot(wt, fake_host)
    assert "port_busy" not in fake_host.calls


def test_busy_port_skips_slot(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    fake_host.ports_busy |= {443}
    assert ensure_slot(make_worktree("a"), fake_host).slot == 1


def test_foreign_df_skips_slot0(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [owner(project="df", wd=other)]
    assert ensure_slot(wt, fake_host).slot == 1


def test_adopts_own_running_df_without_probe(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    fake_host.projects["df"] = [owner(wd=wt)]
    fake_host.ports_busy |= {80, 443}
    assert ensure_slot(wt, fake_host).slot == 0
    assert "port_busy" not in fake_host.calls


def test_legacy_dev_df_raises_with_hint(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [
        owner(wd=other, config_files=("/x/docker/docker-compose.debug.yaml",))
    ]
    with pytest.raises(SlotError) as ei:
        ensure_slot(wt, fake_host)
    assert (
        "docker compose -p df -f /x/docker/docker-compose.debug.yaml --project-directory"
        in str(ei.value)
    )
    assert not (wt / SLOT_FILE_REL).exists()


def test_eleventh_allocation_errors(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    for i in range(10):
        assert ensure_slot(make_worktree(f"w{i}"), fake_host).slot == i
    with pytest.raises(SlotError, match="slot-release --slot"):
        ensure_slot(make_worktree("x"), fake_host)


def test_stale_reservation_reclaimed_only_without_containers(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = make_worktree("o")
    fake_host.projects["df"] = [owner(wd=other)]
    gone = tmp_path / "gone"
    reserve(_reg(fake_host), 1, gone, "tg", 1)
    fake_host.projects["df-s1"] = [owner(project="df-s1", wd=gone)]
    assert ensure_slot(make_worktree("a"), fake_host).slot == 2
    assert "just test::slot-reap df-s1" in capsys.readouterr().err
    del fake_host.projects["df-s1"]
    b = make_worktree("b")
    assert ensure_slot(b, fake_host).slot == 1
    assert _res(fake_host, 1)["owner"] == str(b)


def test_stale_when_owner_slot_file_names_other_slot(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    w = make_worktree("w")
    reserve(_reg(fake_host), 0, w, "old", 1)
    (w / SLOT_FILE_REL).write_text("DF_SLOT=5\nDF_SLOT_TOKEN=old\n")
    assert ensure_slot(make_worktree("new"), fake_host).slot == 0


def _expire_all_but(
    fake_host: FakeHost, fillers: dict[int, Path], now: float, ages: dict[int, float]
) -> None:
    fake_host.clock_value[0] = now
    for n, wt in fillers.items():
        tok = _slot_kv(wt)["DF_SLOT_TOKEN"]
        reserve(_reg(fake_host), n, wt, tok, int(now - ages.get(n, 1 * DAY)))


def test_idle_reclaim_oldest_expired_first(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_host.projects["df"] = [owner(wd=make_worktree("o"))]
    t0 = fake_host.clock_value[0]
    fillers = fill_slots(fake_host, make_worktree, monkeypatch, range(1, 10), t0)
    now = t0 + 30 * DAY
    _expire_all_but(fake_host, fillers, now, {4: 8 * DAY, 2: 9 * DAY})
    new = make_worktree("new")
    assert ensure_slot(new, fake_host).slot == 2
    assert _res(fake_host, 2)["owner"] == str(new)
    assert _res(fake_host, 2)["last_used"] == str(int(now))


def test_idle_reclaim_skips_fresh_lease_and_stopped_containers(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_host.projects["df"] = [owner(wd=make_worktree("o"))]
    t0 = fake_host.clock_value[0]
    fillers = fill_slots(fake_host, make_worktree, monkeypatch, range(1, 10), t0)
    _expire_all_but(fake_host, fillers, t0 + 30 * DAY, {9: 20 * DAY})
    fake_host.projects["df-s9"] = [owner(project="df-s9", wd=fillers[9], running=False)]
    with pytest.raises(SlotError, match="slot-claim"):
        ensure_slot(make_worktree("new"), fake_host)
    assert _res(fake_host, 9)["owner"] == str(fillers[9])


def test_former_owner_reallocates_with_notice(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_host.projects["df"] = [owner(wd=make_worktree("o"))]
    t0 = fake_host.clock_value[0]
    fillers = fill_slots(fake_host, make_worktree, monkeypatch, range(1, 10), t0)
    _expire_all_but(
        fake_host, fillers, t0 + 30 * DAY, {n: 10 * DAY + n for n in range(1, 10)}
    )
    capsys.readouterr()
    assert ensure_slot(make_worktree("new"), fake_host).slot == 9
    e = ensure_slot(fillers[9], fake_host)
    assert e.slot == 8
    assert "slot 9 was reclaimed while idle; now slot 8" in capsys.readouterr().err
    assert _slot_kv(fillers[9])["DF_SLOT"] == "8"


def test_former_owner_with_containers_raises(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("b")
    e = ensure_slot(wt, fake_host)
    reserve(_reg(fake_host), e.slot, other, "stolen", 1)
    fake_host.projects[e.project] = [owner(project=e.project, wd=wt)]
    with pytest.raises(
        SlotError, match=re.escape(f"slot {e.slot} now belongs to {other}")
    ):
        ensure_slot(wt, fake_host)


def test_df_takeover_names_hijacker(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt, other = make_worktree("a"), make_worktree("hijacker")
    assert ensure_slot(wt, fake_host).slot == 0
    fake_host.projects["df"] = [
        owner(wd=other, config_files=("/h/docker/docker-compose.test.yaml",))
    ]
    for fn in (read_slot, ensure_slot):
        with pytest.raises(SlotError) as ei:
            fn(wt, fake_host)
        msg = str(ei.value)
        assert (
            str(other) in msg
            and "/h/docker/docker-compose.test.yaml" in msg
            and "merge main" in msg
        )


def test_requested_slot_free_and_taken(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    assert ensure_slot(make_worktree("a"), fake_host).slot == 3
    with pytest.raises(SlotError, match="slot 3"):
        ensure_slot(make_worktree("b"), fake_host)
    monkeypatch.delenv("DF_SLOT")
    assert ensure_slot(make_worktree("c"), fake_host, requested=5).slot == 5


def test_lease_rewritten_every_ensure(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    fake_host.clock_value[0] = 100
    ensure_slot(wt, fake_host)
    ino = (wt / SLOT_FILE_REL).stat().st_ino
    fake_host.clock_value[0] = 200
    ensure_slot(wt, fake_host)
    assert _res(fake_host, 0)["last_used"] == "200"
    assert (wt / SLOT_FILE_REL).stat().st_ino == ino


def test_ensure_preserves_background(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    p = wt / SLOT_FILE_REL
    p.write_text(p.read_text().replace("DF_BACKGROUND=1", "DF_BACKGROUND=0"))
    assert ensure_slot(wt, fake_host).background is False
    assert _slot_kv(wt)["DF_BACKGROUND"] == "0"


def test_pre_up_recheck_refuses_after_claim(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    env = ensure_slot(a, fake_host)
    reserve(_reg(fake_host), env.slot, b, "new", 1)
    with pytest.raises(SlotError, match="was taken by"):
        lease_and_recheck(env, fake_host)


def test_pre_up_recheck_refreshes_lease(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    env = ensure_slot(make_worktree("a"), fake_host)
    fake_host.clock_value[0] += 500
    lease_and_recheck(env, fake_host)
    assert _res(fake_host, env.slot)["last_used"] == str(int(fake_host.clock_value[0]))


def test_ci_mode_touches_nothing(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    wt = make_worktree("a")
    e = ensure_slot(wt, fake_host)
    assert e == scripts.slots.ci_slot(wt) == read_slot(wt, fake_host)
    lease_and_recheck(e, fake_host)
    assert fake_host.calls == []
    assert not _reg(fake_host).exists() and not (wt / SLOT_FILE_REL).exists()


def test_defaults_resolved_at_call_time(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripts.slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(scripts.slots, "MODULE_ROOT", make_worktree("a"))
    assert ensure_slot().slot == 0
    assert fake_host.calls != []
    assert read_slot().slot == 0


def test_requested_slot_never_idle_reclaims(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    other = make_worktree("other")
    assert ensure_slot(other, fake_host, requested=3).slot == 3
    fake_host.clock_value[0] += 30 * DAY
    with pytest.raises(SlotError, match="slot 3 is not free"):
        ensure_slot(make_worktree("me"), fake_host, requested=3)
    assert _res(fake_host, 3)["owner"] == str(other)


def test_read_slot_returns_validated_registry(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    path = wt / SLOT_FILE_REL
    text = path.read_text().replace(
        f"DF_REGISTRY={_reg(fake_host)}", "DF_REGISTRY=/bogus"
    )
    path.write_text(text)
    assert read_slot(wt, fake_host).registry == _reg(fake_host)
