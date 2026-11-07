import re
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts.slot_tests._helpers import FakeHost, owner, reserve
from scripts.slots import (
    REAP_NAME_RE,
    SLOT_FILE_REL,
    TRANSITION_WARNING,
    SlotError,
    check_background_free,
    claim_slot,
    ensure_slot,
    parse_kv,
    read_slot,
    reap_project,
    release_slot,
    set_background,
    status_report,
)

MakeWt = Callable[[str], Path]


def _reg(h: FakeHost) -> Path:
    return h.common / "df-slots"


def _snapshot(*dirs: Path) -> dict[Path, bytes]:
    return {
        p: p.read_bytes() for d in dirs for p in sorted(d.rglob("*")) if p.is_file()
    }


def test_constants() -> None:
    assert REAP_NAME_RE.match("df-run-0123abcd") and not REAP_NAME_RE.match("df-s10")
    assert "merge main into them first" in TRANSITION_WARNING


def test_background_on_passes_own_project(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "2")
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    fake_host.projects["df-s2"] = [
        owner(project="df-s2", service="discord-bot", wd=wt),
        owner(project="df-s2", service="celery-beat", wd=wt),
    ]
    assert set_background(True, wt, fake_host).background is True
    assert parse_kv((wt / SLOT_FILE_REL).read_text())["DF_BACKGROUND"] == "1"


def test_background_on_refuses_foreign_bot(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "2")
    wt, other = make_worktree("a"), make_worktree("o")
    ensure_slot(wt, fake_host)
    fake_host.projects["df"] = [owner(service="discord-bot", wd=other)]
    with pytest.raises(SlotError, match="discord-bot is already running in project df"):
        set_background(True, wt, fake_host)
    assert parse_kv((wt / SLOT_FILE_REL).read_text())["DF_BACKGROUND"] == "0"


def test_background_proof_env_skips_check(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "2")
    wt, other = make_worktree("a"), make_worktree("o")
    e = ensure_slot(wt, fake_host)
    fake_host.projects["df"] = [owner(service="discord-bot", wd=other)]
    monkeypatch.setenv("DF_BACKGROUND_PROOF", "1")
    assert set_background(True, wt, fake_host).background is True
    check_background_free(e, e.project, fake_host)
    with pytest.raises(SlotError, match="project df"):
        check_background_free(None, "df-dev", fake_host)


def test_background_off_skips_check(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "2")
    wt, other = make_worktree("a"), make_worktree("o")
    ensure_slot(wt, fake_host)
    set_background(True, wt, fake_host)
    fake_host.projects["df"] = [owner(service="celery-beat", wd=other)]
    assert set_background(False, wt, fake_host).background is False
    assert parse_kv((wt / SLOT_FILE_REL).read_text())["DF_BACKGROUND"] == "0"


def test_background_persists_and_survives_ensure(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    set_background(True, wt, fake_host)
    assert ensure_slot(wt, fake_host).background is True


def test_claim_requires_zero_containers_and_free_ports(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    assert ensure_slot(b, fake_host).slot == 1
    fake_host.projects["df"] = [owner(wd=a)]
    with pytest.raises(SlotError, match="slot 0 has 1 container"):
        claim_slot(0, b, fake_host)
    fake_host.projects["df"] = []
    fake_host.ports_busy |= {443}
    with pytest.raises(SlotError, match="port 443 is busy"):
        claim_slot(0, b, fake_host)
    assert read_slot(b, fake_host).slot == 1 and read_slot(a, fake_host).slot == 0


def test_claim_releases_current_first_then_reserves(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    ensure_slot(b, fake_host)
    e = claim_slot(0, b, fake_host)
    assert (e.slot, e.project) == (0, "df")
    assert read_slot(b, fake_host).slot == 0
    assert not (_reg(fake_host) / "slot-1").exists()
    with pytest.raises(SlotError, match="slot 0 now belongs to"):
        read_slot(a, fake_host)
    capsys.readouterr()
    assert ensure_slot(a, fake_host).slot == 1
    assert "slot 0 was reclaimed while idle; now slot 1" in capsys.readouterr().err


def test_claim_refuses_while_own_slot_has_containers(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    ensure_slot(b, fake_host)
    (_reg(fake_host) / "slot-0").unlink()
    (a / SLOT_FILE_REL).unlink()
    fake_host.projects["df-s1"] = [owner(project="df-s1", wd=b)]
    before = _snapshot(_reg(fake_host), b / "docker")
    with pytest.raises(SlotError, match="just test::down"):
        claim_slot(0, b, fake_host)
    assert _snapshot(_reg(fake_host), b / "docker") == before


def test_claim_own_slot_is_noop(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    e = ensure_slot(wt, fake_host)
    fake_host.projects["df"] = [owner(wd=wt)]
    assert claim_slot(0, wt, fake_host).token == e.token


def test_release_refuses_with_containers(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    fake_host.projects["df"] = [owner(wd=wt)]
    with pytest.raises(SlotError, match="just test::down"):
        release_slot(wt, fake_host)
    assert (wt / SLOT_FILE_REL).exists() and (_reg(fake_host) / "slot-0").exists()


def test_release_removes_both_files(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    e = ensure_slot(wt, fake_host)
    release_slot(wt, fake_host)
    assert not (wt / SLOT_FILE_REL).exists()
    assert not (_reg(fake_host) / f"slot-{e.slot}").exists()


def test_release_without_slot_file_drops_own_reservation(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    reserve(_reg(fake_host), 4, wt, "t4", 1)
    release_slot(wt, fake_host)
    assert not (_reg(fake_host) / "slot-4").exists()


def test_release_after_reservation_missing(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    wt = make_worktree("a")
    e = ensure_slot(wt, fake_host)
    (_reg(fake_host) / f"slot-{e.slot}").unlink()
    release_slot(wt, fake_host)
    assert not (wt / SLOT_FILE_REL).exists()
    assert f"slot {e.slot} reservation was already gone" in capsys.readouterr().err


def test_release_when_reservation_taken_leaves_it(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    wt, other = make_worktree("a"), make_worktree("b")
    e = ensure_slot(wt, fake_host)
    reserve(_reg(fake_host), e.slot, other, "x", 1)
    release_slot(wt, fake_host)
    assert not (wt / SLOT_FILE_REL).exists()
    assert f"owner={other}" in (_reg(fake_host) / f"slot-{e.slot}").read_text()
    assert f"now belongs to {other}; left it alone" in capsys.readouterr().err


def test_release_other_slot_only_deletes_registry(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    n = ensure_slot(a, fake_host).slot
    ensure_slot(b, fake_host)
    release_slot(b, fake_host, slot=n)
    assert (a / SLOT_FILE_REL).exists()
    assert not (_reg(fake_host) / f"slot-{n}").exists()
    assert read_slot(b, fake_host).slot == 1
    with pytest.raises(SlotError):
        read_slot(a, fake_host)


def test_release_other_slot_refuses_with_containers(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    fake_host.projects["df"] = [owner(wd=a)]
    with pytest.raises(SlotError, match="slot 0 has 1 container"):
        release_slot(b, fake_host, slot=0)
    assert (_reg(fake_host) / "slot-0").exists()


def test_reap_refuses_bad_names(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    for p in ["web", "df-s10", "df-run-xyz", "df-sx", ""]:
        with pytest.raises(SlotError, match="refusing"):
            reap_project(p, wt, fake_host)
    assert fake_host.compose_calls == []


def test_reap_refuses_live_worktree_owner(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, live = make_worktree("me"), make_worktree("live")
    fake_host.projects["df"] = [owner(wd=live)]
    with pytest.raises(SlotError, match=re.escape(str(live))):
        reap_project("df", me, fake_host)
    assert fake_host.compose_calls == []


def test_reap_allows_gone_owner(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    me, gone = make_worktree("me"), tmp_path / "gone"
    reserve(_reg(fake_host), 0, gone, "t", 1)
    fake_host.projects["df"] = [owner(wd=gone)]
    reap_project("df", me, fake_host)
    assert fake_host.compose_calls == [
        ["docker", "compose", "-p", "df", "down", "-v", "--remove-orphans"]
    ]
    assert not (_reg(fake_host) / "slot-0").exists()


def test_reap_oneoff_from_live_worktree_does_not_block(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me = make_worktree("me")
    fake_host.projects["df-run-0123abcd"] = [
        owner(project="df-run-0123abcd", wd=me, oneoff=True)
    ]
    reap_project("df-run-0123abcd", me, fake_host)
    assert fake_host.compose_calls[0][3] == "df-run-0123abcd"


def test_reap_compose_failure_keeps_reservation(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    me = make_worktree("me")
    reserve(_reg(fake_host), 3, tmp_path / "gone", "t", 1)
    fake_host.run_outputs.append((1, ""))
    with pytest.raises(SlotError, match="exited 1"):
        reap_project("df-s3", me, fake_host)
    assert (_reg(fake_host) / "slot-3").exists()


def test_status_live_unreserved_owner_gets_no_reap_hint(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me, live = make_worktree("me"), make_worktree("user-strip-league-stats")
    fake_host.projects["df"] = [
        owner(service="nginx", wd=live),
        owner(name="df-backend-run-1", service="backend", wd=live, oneoff=True),
    ]
    out = status_report(me, fake_host)
    assert f"unreserved (owner live: {live})" in out
    assert "slot-reap df" not in out
    assert not _reg(fake_host).exists() and not (me / SLOT_FILE_REL).exists()


def test_status_creates_no_files_and_flags_orphan(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    me = make_worktree("me")
    fake_host.projects["df-s5"] = [
        owner(project="df-s5", wd=tmp_path / "gone", config_files=("/g/test.yaml",))
    ]
    out = status_report(me, fake_host)
    assert "orphan" in out and "just test::slot-reap df-s5" in out
    assert str(tmp_path / "gone") in out and "/g/test.yaml" in out
    assert not _reg(fake_host).exists() and not (me / SLOT_FILE_REL).exists()


def test_status_oneoff_only_is_hint_not_owner(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    me = make_worktree("me")
    fake_host.projects["df"] = [owner(name="df-backend-run-1", wd=me, oneoff=True)]
    out = status_report(me, fake_host)
    line = next(ln for ln in out.splitlines() if ln.startswith("project df "))
    assert "one-off only" in line and "owner live" not in line


def test_status_lists_registry_rows(
    fake_host: FakeHost, make_worktree: MakeWt, tmp_path: Path
) -> None:
    a = make_worktree("a")
    ensure_slot(a, fake_host)
    fake_host.projects["df"] = [owner(wd=a)]
    reserve(_reg(fake_host), 2, tmp_path / "gone", "t", 1)
    reserve(_reg(fake_host), 3, make_worktree("idle"), "t", 1)
    fake_host.clock_value[0] += 30 * 86_400
    before = _snapshot(_reg(fake_host))
    out = status_report(a, fake_host)
    rows = {ln.split()[1]: ln for ln in out.splitlines() if ln.startswith("slot ")}
    assert "live" in rows["0"] and "containers=1" in rows["0"] and str(a) in rows["0"]
    assert "stale" in rows["2"]
    assert "idle" in rows["3"]
    assert "slot 0" in next(
        ln for ln in out.splitlines() if ln.startswith("project df ")
    )
    assert _snapshot(_reg(fake_host)) == before
