import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

import scripts.slots as slots
from scripts.slot_tests._helpers import REG, ROOTX, FakeHost, owner, reserve
from scripts.slots import (
    SLOT_FILE_REL,
    NoSlotFile,
    SlotError,
    compose_argv,
    compose_cmd,
    compose_env,
    compose_files,
    ensure_slot,
    prepare,
    run_one_off,
    slot_env_for,
    split_verb,
)

MakeWt = Callable[[str], Path]
SCALE = ["--scale", "celery-beat=0", "--scale", "discord-bot=0"]


def _files(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-f"]


def _project(argv: list[str]) -> str:
    return argv[argv.index("-p") + 1]


def test_split_verb_skips_global_options() -> None:
    assert split_verb(["--ansi", "always", "up", "-d"]) == (
        ["--ansi", "always"],
        "up",
        ["-d"],
    )
    assert split_verb(["--progress=plain", "--profile", "x", "down"]) == (
        ["--progress=plain", "--profile", "x"],
        "down",
        [],
    )
    assert split_verb(["-d"]) == (["-d"], None, [])


def test_ansi_up_allocates_checks_and_scales(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    argv, env = prepare(
        "test", ["--ansi", "always", "up", "-d"], root=wt, host=fake_host
    )
    assert (fake_host.common / "df-slots" / "slot-3").exists()
    assert 13443 in fake_host.probed_ports
    i = argv.index("up")
    assert (
        argv[i - 2 : i] == ["--ansi", "always"]
        and argv[i + 1 : i + 5] == SCALE
        and argv[-1] == "-d"
    )
    assert env["COMPOSE_PROJECT_NAME"] == "df-s3"


def test_create_gets_scale(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    argv, _ = prepare("test", ["create"], root=wt, host=fake_host)
    assert argv[argv.index("create") + 1 :][:4] == SCALE


def test_dev_ansi_up_runs_dev_checks(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [owner(service="discord-bot", wd=other)]
    with pytest.raises(SlotError, match="discord-bot is already running in project df"):
        prepare(
            "dev",
            ["--ansi", "always", "up", "--no-attach", "nginx"],
            root=wt,
            host=fake_host,
        )
    assert {80, 443} <= set(fake_host.probed_ports) and fake_host.compose_calls == []
    assert not (wt / SLOT_FILE_REL).exists()


def test_proof_lets_prepare_up_pass_foreign_bot(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt, other = make_worktree("a"), make_worktree("o")
    ensure_slot(wt, fake_host)
    monkeypatch.setenv("DF_BACKGROUND_PROOF", "1")
    slots.set_background(True, wt, fake_host)
    fake_host.projects["df"] = [owner(service="discord-bot", wd=other)]
    argv, _ = prepare("test", ["up", "-d"], root=wt, host=fake_host)
    assert (
        "--scale" not in argv
        and str(wt / "docker/docker-compose.slot-offline.yaml") in argv
    )


def test_compose_env_overrides_stale_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "df")
    monkeypatch.setenv("DF_BASE_URL", "https://localhost")
    env = compose_env("test", slot_env_for(3, ROOTX, "t", REG))
    assert (env["COMPOSE_PROJECT_NAME"], env["DF_BASE_URL"]) == (
        "df-s3",
        "https://localhost:13443",
    )


def test_prepare_down_without_slot_names_fix(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    with pytest.raises(NoSlotFile, match="just test::slot"):
        prepare("test", ["down"], root=make_worktree("a"), host=fake_host)


def test_prepare_run_verb_raises(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    with pytest.raises(SlotError, match="use run_one_off"):
        prepare("test", ["run", "backend"], root=make_worktree("a"), host=fake_host)


def test_prepare_unknown_verb_requires_slot(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    with pytest.raises(NoSlotFile):
        prepare("test", ["frobnicate"], root=make_worktree("a"), host=fake_host)


def test_ci_outside_runner_only_config(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    wt = make_worktree("a")
    with pytest.raises(SlotError, match="only `config` is allowed"):
        prepare(
            "test",
            ["exec", "-T", "redis", "redis-cli", "FLUSHALL"],
            root=wt,
            host=fake_host,
        )
    argv, _ = prepare("test", ["config"], root=wt, host=fake_host)
    assert argv[argv.index("-p") + 1] == "df" and fake_host.calls == []


DEV_VERBS = [["down"], ["--ansi", "always", "up", "-d"], ["logs"]]
DBG = ("/x/docker/docker-compose.debug.yaml",)


@pytest.mark.parametrize("args", DEV_VERBS)
def test_dev_guard_refuses_foreign(
    fake_host: FakeHost, make_worktree: MakeWt, args: list[str]
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df-dev"] = [
        owner(project="df-dev", service="backend", wd=other, config_files=DBG)
    ]
    with pytest.raises(SlotError, match=re.escape(f"`df-dev` belongs to {other}")):
        prepare("dev", args, root=wt, host=fake_host)
    assert fake_host.compose_calls == [] and not (wt / SLOT_FILE_REL).exists()


@pytest.mark.parametrize("own", [True, False], ids=["own", "empty"])
@pytest.mark.parametrize("args", DEV_VERBS)
def test_dev_guard_passes_own_or_empty(
    fake_host: FakeHost, make_worktree: MakeWt, args: list[str], own: bool
) -> None:
    wt = make_worktree("a")
    fake_host.projects["df-dev"] = (
        [owner(project="df-dev", service="nginx", wd=wt, config_files=DBG)]
        if own
        else []
    )
    argv, env = prepare("dev", args, root=wt, host=fake_host)
    assert argv[argv.index("-p") + 1] == "df-dev" and not any(
        k.startswith("DF_") for k in env
    )
    assert fake_host.compose_calls == [] and not (wt / SLOT_FILE_REL).exists()


def test_dev_legacy_df_prints_cleanup_hint(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [owner(service="backend", wd=other, config_files=DBG)]
    prepare("dev", ["down"], root=wt, host=fake_host)
    err = capsys.readouterr().err
    assert "legacy dev stack" in err and f"--project-directory {other} down" in err
    prepare("dev", ["logs"], root=wt, host=fake_host)
    assert "legacy dev stack" not in capsys.readouterr().err


def test_prepare_up_refuses_when_slot_taken_mid_command(
    fake_host: FakeHost,
    make_worktree: MakeWt,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    a, b = make_worktree("a"), make_worktree("b")
    held = ensure_slot(a, fake_host)
    monkeypatch.delenv("DF_SLOT")
    reserve(
        fake_host.common / "df-slots", 3, b, "theirs", int(fake_host.clock_value[0])
    )
    before = (a / SLOT_FILE_REL).read_text()
    with pytest.raises(SlotError, match="slot 3 was taken by"):
        prepare(
            "test", ["--ansi", "always", "up", "-d"], root=a, host=fake_host, slot=held
        )
    assert fake_host.compose_calls == [] and (a / SLOT_FILE_REL).read_text() == before
    assert "reclaimed while idle" not in capsys.readouterr().err


def test_prepare_with_held_slot_skips_allocation(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    held = ensure_slot(wt, fake_host)
    (wt / SLOT_FILE_REL).unlink()
    argv, _ = prepare("test", ["down"], root=wt, host=fake_host, slot=held)
    assert _project(argv) == "df-s3" and not (wt / SLOT_FILE_REL).exists()


def test_run_one_off_with_slot_stops_only_new_services(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/podman.sock")
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    fake_host.run_outputs = [
        (0, "redis\nnginx\n"),
        (5, ""),
        (0, "redis\nnginx\nbackend\n"),
        (0, ""),
        (0, ""),
    ]
    assert run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host) == 5
    calls = fake_host.compose_calls
    assert all(c[c.index("-p") + 1] == "df-s3" for c in calls)
    assert calls[1][calls[1].index("run") :] == ["run", "--rm", "backend", "true"]
    assert calls[3][calls[3].index("stop") :] == ["stop", "backend"]
    assert calls[4][calls[4].index("rm") :] == ["rm", "-f", "backend"]
    for e in fake_host.run_envs:
        assert (
            e["PATH"]
            and e["DOCKER_HOST"] == "unix:///run/podman.sock"
            and e["COMPOSE_PROJECT_NAME"] == "df-s3"
        )


def test_run_one_off_cleans_up_when_run_raises(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    outputs = iter(
        [(0, "redis\n"), KeyboardInterrupt(), (0, "redis\nbackend\n"), (0, ""), (0, "")]
    )
    seen: list[list[str]] = []

    def run(argv: list[str], env: dict[str, str], capture: bool) -> tuple[int, str]:
        seen.append(argv)
        out = next(outputs)
        if isinstance(out, BaseException):
            raise out
        return out

    monkeypatch.setattr(fake_host, "run", run)
    with pytest.raises(KeyboardInterrupt):
        run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host)
    assert seen[-1][seen[-1].index("rm") :] == ["rm", "-f", "backend"]


def test_run_one_off_mismatched_slot_propagates(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    shutil.copy(a / SLOT_FILE_REL, b / SLOT_FILE_REL)
    with pytest.raises(SlotError, match="was written for"):
        run_one_off(["--rm", "backend", "true"], root=b, host=fake_host)
    assert fake_host.compose_calls == []


def test_run_one_off_without_slot_uses_ephemeral_project(
    fake_host: FakeHost, make_worktree: MakeWt, capsys: pytest.CaptureFixture[str]
) -> None:
    wt = make_worktree("a")
    run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host)
    assert "Discord/Steam tokens are blanked" in capsys.readouterr().err
    first, last = fake_host.compose_calls[0], fake_host.compose_calls[-1]
    assert re.fullmatch(r"df-run-[0-9a-f]{8}", first[first.index("-p") + 1])
    assert str(wt / "docker/docker-compose.run.yaml") in first
    assert (
        last[-3:] == ["down", "-v", "--remove-orphans"]
        and last[last.index("-p") + 1] == first[first.index("-p") + 1]
    )
    assert (
        not (fake_host.common / "df-slots").exists()
        and not (wt / SLOT_FILE_REL).exists()
    )
    env = fake_host.run_envs[0]
    assert env["DF_SUFFIX"] == f"-{_project(first)[3:]}" and env["DF_HTTPS_PORT"] == "0"


def test_run_one_off_ci_runs_once_without_cleanup(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", "/tmp/r")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/tmp/w")
    wt = make_worktree("a")
    fake_host.run_outputs = [(3, "")]
    assert run_one_off(["--rm", "backend", "true"], root=wt, host=fake_host) == 3
    (call,) = fake_host.compose_calls
    assert _project(call) == "df" and _files(call)[-1].endswith(
        "docker-compose.ci.override.yaml"
    )
    assert fake_host.calls == ["run"]


def test_slot0_legacy_argv_equality() -> None:
    e = slot_env_for(0, ROOTX, "t", REG)
    assert compose_argv("test", "up", "-d", "--remove-orphans", slot=e, root=ROOTX) == [
        "docker",
        "compose",
        "--project-directory",
        str(ROOTX),
        "-p",
        "df",
        "-f",
        str(ROOTX / "docker/docker-compose.test.yaml"),
        "up",
        "-d",
        "--remove-orphans",
    ]


def test_slot_n_up_adds_offline_and_scale() -> None:
    argv = compose_argv(
        "test", "up", "-d", slot=slot_env_for(3, ROOTX, "t", REG), root=ROOTX
    )
    assert _files(argv) == [
        str(ROOTX / "docker/docker-compose.test.yaml"),
        str(ROOTX / "docker/docker-compose.slot.yaml"),
        str(ROOTX / "docker/docker-compose.slot-offline.yaml"),
    ]
    assert argv[argv.index("up") + 1 :] == [*SCALE, "-d"] and _project(argv) == "df-s3"


def test_slot_n_background_on_omits_offline_and_scale() -> None:
    e = slot_env_for(3, ROOTX, "t", REG, background=True)
    argv = compose_argv("test", "up", "-d", slot=e, root=ROOTX)
    assert (
        not any(f.endswith("slot-offline.yaml") for f in _files(argv))
        and "--scale" not in argv
    )


def test_proof_env_adds_offline_with_background_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DF_BACKGROUND_PROOF", "1")
    e = slot_env_for(3, ROOTX, "t", REG, background=True)
    files = compose_files("test", e, ROOTX)
    assert files[-1] == ROOTX / "docker/docker-compose.slot-offline.yaml"


def test_scale_only_on_up_and_create() -> None:
    e = slot_env_for(3, ROOTX, "t", REG)
    for verb in ("down", "build", "pull", "logs"):
        assert "--scale" not in compose_argv("test", verb, slot=e, root=ROOTX), verb


@pytest.mark.parametrize("verb", ["down", "stop", "kill", "rm"])
def test_teardown_verbs_reach_profiled_services(verb: str) -> None:
    # The dota-lobby simulator sits behind a profile: without it, `down`
    # leaves its container holding the project's network.
    for n in (0, 3):
        e = slot_env_for(n, ROOTX, "t", REG)
        argv = compose_argv("test", verb, "-v", slot=e, root=ROOTX)
        assert argv[argv.index(verb) - 2 :] == ["--profile", "*", verb, "-v"], (n, verb)


def test_profiles_stay_off_for_other_verbs_and_stacks() -> None:
    e = slot_env_for(3, ROOTX, "t", REG)
    for verb in ("up", "create", "logs", "ps", "restart", "config"):
        assert "--profile" not in compose_argv("test", verb, slot=e, root=ROOTX), verb
    assert "--profile" not in compose_argv("dev", "down", root=ROOTX)
    # An explicit --profile is left as it is.
    argv = compose_argv("test", "--profile", "x", "down", slot=e, root=ROOTX)
    assert argv.count("--profile") == 1 and argv[argv.index("--profile") + 1] == "x"


@pytest.mark.parametrize("stack", ["test", "dev", "dev-m1", "prod", "release"])
def test_all_f_paths_absolute(stack: slots.Stack) -> None:
    e = slot_env_for(3, ROOTX, "t", REG) if stack == "test" else None
    files = _files(compose_argv(stack, "config", slot=e, root=ROOTX))
    assert files and all(Path(f).is_absolute() for f in files)


def test_compose_argv_test_without_slot_raises_outside_ci() -> None:
    with pytest.raises(SlotError):
        compose_argv("test", "down", root=ROOTX)


def test_ci_mode_argv(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", "/tmp/r")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/tmp/w")
    wt = make_worktree("a")
    argv, env = prepare(
        "test",
        ["exec", "-T", "redis", "redis-cli", "FLUSHALL"],
        root=wt,
        host=fake_host,
    )
    assert _project(argv) == "df" and env["COMPOSE_PROJECT_NAME"] == "df"
    assert _files(argv) == [
        str(wt / "docker/docker-compose.test.yaml"),
        str(wt / "docker/docker-compose.ci.override.yaml"),
    ]
    assert "--scale" not in argv and fake_host.calls == []
    up, _ = prepare("test", ["up", "-d"], root=wt, host=fake_host)
    assert "--scale" not in up and fake_host.calls == []


def test_dev_and_m1_argv() -> None:
    dev = compose_argv("dev", "up", root=ROOTX)
    m1 = compose_argv("dev-m1", "up", root=ROOTX)
    assert _project(dev) == _project(m1) == "df-dev"
    assert _files(dev) == [str(ROOTX / "docker/docker-compose.debug.yaml")]
    assert _files(m1) == [str(ROOTX / "docker/docker-compose.debug.m1.yaml")]
    assert "--scale" not in dev


def test_release_argv() -> None:
    assert compose_argv("release", "up", "-d", root=ROOTX) == [
        "docker",
        "compose",
        "--project-directory",
        str(ROOTX),
        "-p",
        "df",
        "-f",
        str(ROOTX / "docker/docker-compose.release.yaml"),
        "up",
        "-d",
    ]
    assert _files(compose_argv("prod", "up", root=ROOTX)) == [
        str(ROOTX / "docker/docker-compose.prod.yaml")
    ]


def test_compose_cmd_is_shell_joined() -> None:
    assert compose_cmd(
        "dev", "exec", "backend", "sh", "-c", "a b", root=ROOTX
    ).endswith("exec backend sh -c 'a b'")


@pytest.mark.parametrize("stack", ["dev", "dev-m1", "prod", "release"])
def test_dev_prod_release_bypass(
    stack: slots.Stack, fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    argv, env = prepare(stack, ["up", "-d"], root=wt, host=fake_host)
    assert env == {"COMPOSE_PROJECT_NAME": _project(argv)}
    assert (
        not (wt / SLOT_FILE_REL).exists()
        and not (fake_host.common / "df-slots").exists()
    )
    if stack in ("prod", "release"):
        assert "port_busy" not in fake_host.calls and _project(argv) == "df"


@pytest.mark.parametrize("stack", ["prod", "release"])
@pytest.mark.parametrize(
    "cfg", ["docker-compose.test.yaml", "docker-compose.debug.yaml"]
)
def test_prod_guard(
    stack: slots.Stack, cfg: str, fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt, other = make_worktree("a"), make_worktree("o")
    fake_host.projects["df"] = [owner(wd=other, config_files=(f"/x/docker/{cfg}",))]
    with pytest.raises(SlotError, match=re.escape(str(other))):
        prepare(stack, ["down"], root=wt, host=fake_host)


def test_prod_guard_passes_prod_containers(
    fake_host: FakeHost, make_worktree: MakeWt
) -> None:
    wt = make_worktree("a")
    fake_host.projects["df"] = [
        owner(wd=wt, config_files=("/x/docker/docker-compose.release.yaml",))
    ]
    argv, _ = prepare("release", ["up", "-d"], root=wt, host=fake_host)
    assert _project(argv) == "df"


def test_dev_up_busy_port_aborts(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    fake_host.ports_busy = {443}
    with pytest.raises(SlotError, match="port 443 is busy"):
        prepare("dev", ["up", "-d"], root=wt, host=fake_host)
    assert fake_host.compose_calls == []


def test_test_up_busy_port_aborts(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    ensure_slot(wt, fake_host)
    fake_host.ports_busy = {13443}
    with pytest.raises(SlotError, match="port 13443 is busy"):
        prepare("test", ["up", "-d"], root=wt, host=fake_host)


def test_own_port_counts_free(fake_host: FakeHost, make_worktree: MakeWt) -> None:
    wt = make_worktree("a")
    fake_host.projects["df"] = [owner(service="nginx", wd=wt)]
    fake_host.ports_busy = {443}
    argv, _ = prepare("test", ["up", "-d"], root=wt, host=fake_host)
    assert argv[argv.index("-p") : argv.index("-p") + 2] == ["-p", "df"]


def test_flush_refuses_after_reclaim(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    a, b = make_worktree("a"), make_worktree("b")
    ensure_slot(a, fake_host)
    monkeypatch.delenv("DF_SLOT")
    reserve(
        fake_host.common / "df-slots", 3, b, "theirs", int(fake_host.clock_value[0])
    )
    with pytest.raises(SlotError, match="now belongs to"):
        prepare(
            "test",
            ["exec", "-T", "redis", "redis-cli", "FLUSHALL"],
            root=a,
            host=fake_host,
        )


def test_compose_argv_refuses_project_override() -> None:
    slot = slot_env_for(3, ROOTX, "t", REG)
    with pytest.raises(SlotError, match="not allowed"):
        compose_argv("test", "--project-name=df", "down", slot=slot, root=ROOTX)


def test_prepare_refuses_project_override_before_allocating(
    fake_host: FakeHost, make_worktree: MakeWt, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    wt = make_worktree("a")
    with pytest.raises(SlotError, match="not allowed"):
        prepare("test", ["-p", "df", "up", "-d"], root=wt, host=fake_host)
    assert not (fake_host.common / "df-slots" / "slot-3").exists()
    assert fake_host.compose_calls == []
