import shlex
from collections.abc import Callable
from pathlib import Path

import pytest
from invoke import MockContext, Result
from invoke.exceptions import Exit

import scripts.compose
import scripts.slots as slots
import scripts.tests as st
import tasks
from scripts.compose import playwright_env, run_compose
from scripts.slot_tests._helpers import FakeHost, owner
from scripts.slots import SLOT_FILE_REL, NoSlotFile
from scripts.tests import flush_test_redis


class RecCtx(MockContext):
    # invoke's Context is a DataProxy: plain attribute writes copy into the config
    def __init__(self, log: list[str] | None = None) -> None:
        super().__init__()
        object.__setattr__(self, "cmds", [])
        object.__setattr__(self, "envs", [])
        object.__setattr__(self, "kws", [])
        object.__setattr__(self, "log", log if log is not None else [])

    def run(self, command: str, **kw: object) -> Result:
        self.cmds.append(command)
        self.envs.append(dict(kw.get("env") or {}))
        self.kws.append(dict(kw))
        self.log.append(command)
        return Result(command=command)


def _ci(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_TEMP": "/tmp/r",
        "GITHUB_WORKSPACE": "/tmp/w",
    }.items():
        monkeypatch.setenv(k, v)


def test_recctx_shares_the_callers_list() -> None:
    shared: list[str] = []
    c = RecCtx(shared)
    c.run("echo hi")
    assert c.log is shared and shared == ["echo hi"] and c.cmds == ["echo hi"]


@pytest.fixture
def slotless(
    monkeypatch: pytest.MonkeyPatch,
    fake_host: FakeHost,
    make_worktree: Callable[[str], Path],
) -> tuple[Path, FakeHost]:
    root = make_worktree("a")
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    return root, fake_host


def test_run_compose_down_without_slot_never_runs(
    slotless: tuple[Path, FakeHost],
) -> None:
    with pytest.raises(Exit):
        run_compose(MockContext(), "test", "down")


def test_test_down_is_scoped(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    c = RecCtx()
    run_compose(c, "test", "down", "--remove-orphans")
    assert " -p df-s3 " in c.cmds[0] and c.cmds[0].endswith("down --remove-orphans")
    assert c.envs[0]["COMPOSE_PROJECT_NAME"] == "df-s3"


def test_playwright_env_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    _ci(monkeypatch)
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    assert playwright_env() == {
        "DF_BASE_URL": "https://localhost",
        "DF_BASE_URL_SOURCE": "invoke",
        "DOCKER_HOST": "localhost",
    }


def test_playwright_env_local_slot(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    assert playwright_env() == {
        "DF_BASE_URL": "https://localhost:13443",
        "DF_BASE_URL_SOURCE": "invoke",
        "DOCKER_HOST": "localhost",
    }


def test_playwright_env_local_without_slot_refuses(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripts.compose, "in_container", lambda: False)
    with pytest.raises((NoSlotFile, Exit)):
        playwright_env()


def test_playwright_env_container(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripts.compose, "in_container", lambda: True)
    assert playwright_env() == {
        "DF_BASE_URL": "https://nginx",
        "DF_BASE_URL_SOURCE": "container",
        "DOCKER_HOST": "nginx",
    }
    assert slotless[1].calls == []


def test_test_run_splits_cmd(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    seen: list[list[str]] = []

    def fake_run_one_off(args: list[str], **_: object) -> int:
        seen.append(list(args))
        return 0

    monkeypatch.setattr(scripts.compose, "run_one_off", fake_run_one_off)
    tasks.test_run(RecCtx(), cmd="python manage.py test x -v 2")
    assert seen[0][:3] == ["--rm", "--entrypoint", ""]
    assert seen[0][-7:] == ["backend", "python", "manage.py", "test", "x", "-v", "2"]


def test_test_run_failure_exits_nonzero(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripts.compose, "run_one_off", lambda args, **_: 3)
    with pytest.raises(Exit) as exc:
        tasks.test_run(RecCtx(), cmd="false")
    assert exc.value.code == 3


def test_test_exec_splits_cmd(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    c = RecCtx()
    tasks.test_exec(c, service="backend", cmd="python manage.py shell")
    assert c.cmds[0].endswith(" exec backend python manage.py shell")
    assert c.kws[0].get("pty") is True


def test_auto_link_argv(slotless: tuple[Path, FakeHost]) -> None:
    c = RecCtx()
    tasks._auto_link_all_tournaments(c, "dev")
    argv = shlex.split(c.cmds[0])
    i = argv.index("exec")
    assert argv[argv.index("-p") + 1] == "df-dev"
    assert argv[i : i + 5] == ["exec", "-T", "backend", "python", "-c"]
    assert "django.setup()" in argv[i + 5] and "{linked}" in argv[i + 5]


def _stub_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "load_dotenv", lambda *a, **k: True)
    monkeypatch.setattr(tasks, "db_migrate", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "docker_release_pull", lambda *a, **k: None)


def test_release_task_argv(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_release(monkeypatch)
    c = RecCtx()
    tasks.dev_release(c)
    rel = f"-p df -f {slots.MODULE_ROOT}/docker/docker-compose.release.yaml"
    assert any(rel in x and x.endswith(" down") for x in c.cmds)
    assert any(rel in x and x.endswith(" up -d") for x in c.cmds)


def test_release_task_refuses_over_test_stack(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, h = slotless
    h.projects["df"] = [
        owner(
            service="nginx",
            wd=root,
            config_files=("/x/docker/docker-compose.test.yaml",),
        )
    ]
    _stub_release(monkeypatch)
    c = RecCtx()
    with pytest.raises(Exit):
        tasks.dev_release(c)
    assert c.cmds == []


def _stub_setup_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "populate_all",
        "update_for_test",
        "docker_build_all",
        "docker_pull_all",
    ):
        monkeypatch.setattr(st, name, lambda *a, **k: None)
    monkeypatch.setattr(st, "load_dotenv", lambda *a, **k: True)


def test_setup_allocates_before_down(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    _stub_setup_steps(monkeypatch)
    ctx = RecCtx()
    real = st.ensure_slot

    def logged_ensure(*a: object, **k: object) -> slots.SlotEnv:
        ctx.log.append("ENSURE")
        return real(*a, **k)

    monkeypatch.setattr(st, "ensure_slot", logged_ensure)
    st.setup(ctx)
    log = ctx.log
    downs = [i for i, x in enumerate(log) if " down" in x]
    ups = [x for x in log if " up" in x]
    assert log[0] == "ENSURE" and log.count("ENSURE") == 1 and downs and downs[0] > 0
    assert " -p df-s3 " in ups[-1]
    assert "--scale celery-beat=0 --scale discord-bot=0" in ups[-1]


def test_dev_test_allocates_in_fresh_worktree(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = slotless
    monkeypatch.setenv("DF_SLOT", "3")
    monkeypatch.setattr(st, "load_dotenv", lambda *a, **k: True)
    c = RecCtx()
    st.dev_test(c)
    assert (root / SLOT_FILE_REL).exists()
    assert " -p df-s3 " in c.cmds[0] and " down" in c.cmds[0]
    assert " -p df-s3 " in c.cmds[-1] and " up --scale " in c.cmds[-1]
    assert c.cmds[-1].endswith(" -d")


def test_flush_test_redis_refuses_without_slot(
    slotless: tuple[Path, FakeHost], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(Exit):
        flush_test_redis(MockContext())
    assert "just test::slot" in capsys.readouterr().err


def test_flush_test_redis_uses_fixture_slot(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    c = RecCtx()
    flush_test_redis(c)
    assert " -p df-s3 " in c.cmds[0]
    assert c.cmds[0].endswith("exec -T redis redis-cli FLUSHALL")


def test_flush_test_redis_ci_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    _ci(monkeypatch)
    c = RecCtx()
    flush_test_redis(c)
    assert " -p df " in c.cmds[0] and "docker-compose.ci.override.yaml" in c.cmds[0]
    assert c.cmds[0].endswith("exec -T redis redis-cli FLUSHALL")


def test_flush_test_redis_is_fatal(
    slotless: tuple[Path, FakeHost], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot()
    c = RecCtx()
    flush_test_redis(c)
    assert not c.kws[0].get("warn")
