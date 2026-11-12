"""Run the real just recipes with a recording python and npx.

DF_JUST_PYTHON points the recipes at a stub that records its cwd, a few env
vars and argv, so these check what each recipe hands to the slot helper,
manage.py and Playwright, including shell quoting, without containers.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")
SLOTS = ["-m", "scripts.slots", "--root", str(ROOT), "compose"]
APPS = ["steam", "app", "bracket", "discordbot", "events", "org", "user", "lobby"]

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")

RECORDER = """#!/usr/bin/env bash
{{
    printf '%s\\0' "$PWD" "${{DISABLE_CACHE-}}" "${{TEST-}}" "${{DF_BASE_URL-}}" "$(basename "$0")" "$@"
    printf '\\036'
}} >> {log}
if [[ "${{1-}} ${{2-}} ${{3-}}" == "-m scripts.compose env" ]]; then
    echo "export DF_BASE_URL='https://localhost:13443'"
    echo "export DF_BASE_URL_SOURCE=runner"
fi
if [[ " $* " == *" compose --stack dev ps backend "* ]]; then
    # The backend reports running from the (DF_FAKE_PS_FAILS+1)th ps on.
    n=$(( $(cat "{log}.ps" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "{log}.ps"
    (( n > ${{DF_FAKE_PS_FAILS:-0}} )) && echo '[{{"State":"running"}}]'
    exit 0
fi
if [[ "${{1-}} ${{2-}}" == "-m scripts.slots" && " $* " == *" ensure "* && -n "${{DF_FAKE_ENSURE_FAIL-}}" ]]; then
    echo "all 10 slots are held" >&2
    exit 1
fi
exit "${{DF_FAKE_EXIT:-0}}"
"""


@dataclass(frozen=True)
class Call:
    cwd: Path
    disable_cache: str
    test: str
    base_url: str
    tool: str
    argv: list[str]


@dataclass
class Runner:
    log: Path
    env: dict[str, str]

    def __call__(
        self, *args: str, exit_code: int = 0, **extra_env: str
    ) -> subprocess.CompletedProcess[str]:
        assert JUST is not None
        self.log.write_bytes(b"")
        Path(f"{self.log}.ps").unlink(missing_ok=True)
        env = {**self.env, "DF_FAKE_EXIT": str(exit_code), **extra_env}
        return subprocess.run(
            [JUST, "--justfile", str(ROOT / "justfile"), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def calls(self) -> list[Call]:
        out = []
        for record in self.log.read_bytes().split(b"\x1e"):
            if not record:
                continue
            cwd, cache, test, url, tool, *argv = record.decode().split("\0")[:-1]
            out.append(Call(Path(cwd), cache, test, url, tool, argv))
        return out

    def dry_run(self, *args: str) -> str:
        assert JUST is not None
        result = subprocess.run(
            [JUST, "--justfile", str(ROOT / "justfile"), "--dry-run", "--no-deps", *args],
            cwd=ROOT,
            env=self.env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stderr


@pytest.fixture
def run(tmp_path: Path) -> Runner:
    log = tmp_path / "calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "npx"):
        stub = bin_dir / name
        stub.write_text(RECORDER.format(log=str(log)))
        stub.chmod(0o755)
    env = {
        **os.environ,
        "DF_JUST_PYTHON": str(bin_dir / "python"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }
    for key in ("TEST", "DISABLE_CACHE", "DF_BASE_URL"):
        env.pop(key, None)
    return Runner(log, env)


SHELL_CMDS = [
    "python manage.py test x -v 2",
    "python manage.py test x 2>&1 | tee /tmp/out && echo $HOME",
    "echo 'unbalanced",
]


@pytest.mark.parametrize("cmd", SHELL_CMDS)
def test_test_run_keeps_shell_semantics(run: Runner, cmd: str) -> None:
    result = run("test::run", cmd)
    assert result.returncode == 0, result.stderr
    [call] = run.calls()
    assert call.cwd == ROOT
    assert call.argv == [*SLOTS, "run", "--rm", "--entrypoint", "", "backend", "sh", "-c", cmd]


def test_test_run_empty_cmd_uses_image_default(run: Runner) -> None:
    assert run("test::run", "").returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, "run", "--rm", "--entrypoint", "", "backend"]


def test_test_run_other_service(run: Runner) -> None:
    assert run("test::run", "ls", "frontend").returncode == 0
    [call] = run.calls()
    assert call.argv[-4:] == ["frontend", "sh", "-c", "ls"]


def test_test_run_failure_exits_nonzero(run: Runner) -> None:
    assert run("test::run", "false", exit_code=3).returncode == 3


@pytest.mark.parametrize("cmd", SHELL_CMDS)
def test_dev_run_keeps_shell_semantics(run: Runner, cmd: str) -> None:
    assert run("dev::run", cmd).returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, "--stack", "dev", "run", "--rm", "backend", "sh", "-c", cmd]


@pytest.mark.parametrize("recipe,stack", [("test::exec", []), ("dev::exec", ["--stack", "dev"]), ("prod::exec", ["--stack", "prod"])])
@pytest.mark.parametrize("cmd", ["python manage.py shell", "cat a > b && echo $X | wc", "echo 'unbalanced"])
def test_exec_keeps_shell_semantics(run: Runner, recipe: str, stack: list[str], cmd: str) -> None:
    assert run(recipe, "backend", cmd).returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, *stack, "exec", "backend", "sh", "-c", cmd]


@pytest.mark.parametrize(
    "recipe,tail",
    [
        ("test::down", ["down", "--remove-orphans"]),
        ("test::upd", ["up", "-d", "--remove-orphans"]),
        ("test::stop", ["stop"]),
        ("test::logs", ["logs", "-f"]),
        ("dev::down", ["--stack", "dev", "down", "--remove-orphans"]),
        ("dev::stop", ["--stack", "dev", "stop"]),
        ("prod::down", ["--stack", "prod", "down", "--remove-orphans"]),
        ("dev::up", ["--stack", "dev", "up", "--remove-orphans"]),
    ],
)
def test_stack_verbs_go_through_the_slot_helper(run: Runner, recipe: str, tail: list[str]) -> None:
    args = ["--no-sync"] if recipe == "dev::up" else []
    assert run(recipe, *args).returncode == 0, recipe
    [call] = run.calls()
    assert call.argv == [*SLOTS, *tail]


@pytest.mark.parametrize(
    "action,tail",
    [
        # The whole stack with the profile on: slots N >= 1 scale services
        # that `up dota-lobby` would leave out of the selection.
        ("up", ["up", "-d"]),
        ("down", ["rm", "--stop", "--force", "dota-lobby"]),
        ("restart", ["restart", "dota-lobby"]),
        ("logs", ["logs", "-f", "dota-lobby"]),
        ("ps", ["ps", "dota-lobby"]),
    ],
)
def test_dota_lobby_simulator_recipe(run: Runner, action: str, tail: list[str]) -> None:
    assert run("test::dota-lobby", action).returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, *tail]


def test_dota_lobby_simulator_recipe_rejects_unknown_actions(run: Runner) -> None:
    result = run("test::dota-lobby", "bogus")
    assert result.returncode == 2 and "usage" in result.stderr
    assert run.calls() == []


def test_test_compose_passes_args_verbatim(run: Runner) -> None:
    assert run("test::compose", "--stack", "dev", "config", "--services").returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, "--stack", "dev", "config", "--services"]


def test_dev_up_rejects_unknown_options(run: Runner) -> None:
    result = run("dev::up", "--bogus")
    assert result.returncode == 2 and "--no-sync" in result.stderr
    assert run.calls() == []


@pytest.mark.parametrize("stack,expected", [(None, "dev"), ("test", "test")])
def test_discord_logs_follows_the_stack(run: Runner, stack: str | None, expected: str) -> None:
    assert run("discord::logs", *([stack] if stack else [])).returncode == 0
    [call] = run.calls()
    assert call.argv == [*SLOTS, "--stack", expected, "logs", "-f", "--tail=100", "discord-bot"]


def test_dev_debug_migrates_with_dev_env_then_starts_dev(run: Runner) -> None:
    assert run("dev::debug").returncode == 0
    calls = run.calls()
    manage = [c for c in calls if c.argv[:1] == ["manage.py"]]
    assert [c.argv for c in manage] == [
        ["manage.py", "makemigrations", *APPS],
        ["manage.py", "migrate"],
    ]
    assert all(c.cwd == ROOT / "backend" and c.test == "false" and c.disable_cache == "true" for c in manage)
    up = calls[-1]
    assert up.argv == [*SLOTS, "--stack", "dev", "--ansi", "always", "up", "--no-attach", "nginx", "--remove-orphans"]
    assert up.test == "false"


def test_migrate_all_uses_each_env(run: Runner) -> None:
    assert run("db::migrate::all").returncode == 0
    migrates = [c for c in run.calls() if c.argv == ["manage.py", "migrate"]]
    assert [c.test for c in migrates] == ["false", "false", "true"]


@pytest.mark.parametrize(
    "args,apps",
    [((), APPS), (("app", "events"), ["app", "events"])],
)
def test_makemigrations_app_list(run: Runner, args: tuple[str, ...], apps: list[str]) -> None:
    assert run("db::makemigrations", *args).returncode == 0
    [call] = run.calls()
    assert call.argv == ["manage.py", "makemigrations", *apps]


def test_populate_users_migrates_test_then_passes_force(run: Runner) -> None:
    assert run("db::populate::users", "--force").returncode == 0
    calls = run.calls()
    assert calls[-1].argv == ["manage.py", "populate_users", "--force"]
    assert all(c.test == "true" and c.cwd == ROOT / "backend" for c in calls)


@pytest.mark.parametrize("flags,force", [((), "False"), (("--force",), "True")])
def test_populate_shell_helpers_pass_force(run: Runner, flags: tuple[str, ...], force: str) -> None:
    assert run("db::populate::demo-tournaments", *flags).returncode == 0
    [call] = run.calls()
    code = f"from tests.populate import populate_demo_tournaments; populate_demo_tournaments(force={force})"
    assert call.argv == ["manage.py", "shell", "-c", code]


def test_populate_rejects_unknown_flags(run: Runner) -> None:
    result = run("db::populate::steam-mock", "--forse")
    assert result.returncode == 2 and run.calls() == []


def test_test_populate_all_is_a_fresh_populate(run: Runner) -> None:
    text = run.dry_run("test::populate::all")
    assert "db::populate::fresh" in text


@pytest.mark.parametrize(
    "args,tail",
    [
        (("version::set", "1.2.3", "--no-commit"), ["-m", "scripts.version", "set", "1.2.3", "--no-commit"]),
        (("version::from-pyproject",), ["-m", "scripts.version", "from-pyproject"]),
        (("demo::create", "shuffle"), ["-m", "scripts.demo", "create", "--spec", "shuffle"]),
        (("demo::gifs", "--fps", "15"), ["-m", "scripts.demo", "gifs", "--fps", "15"]),
        (("test::demo::trim", "--no-auto"), ["-m", "scripts.demo", "trim", "--no-auto"]),
    ],
)
def test_python_cli_recipes(run: Runner, args: tuple[str, ...], tail: list[str]) -> None:
    assert run(*args).returncode == 0
    [call] = run.calls()
    assert call.cwd == ROOT and call.argv == tail


def test_playwright_runs_in_frontend_with_the_slot_url(run: Runner) -> None:
    result = run("test::pw::cicd-chromium", "--shard=1/4")
    assert result.returncode == 0, result.stderr
    env_call, flush_call, npx = run.calls()
    assert env_call.argv == ["-m", "scripts.compose", "env"]
    assert flush_call.argv == ["-m", "scripts.compose", "flush-redis"]
    assert npx.tool == "npx" and npx.cwd == ROOT / "frontend"
    assert npx.base_url == "https://localhost:13443"
    assert npx.argv == ["playwright", "test", "--grep", "@cicd", "--project=chromium", "--no-deps", "--shard=1/4"]


def test_playwright_grep_keeps_spaces(run: Runner) -> None:
    assert run("test::pw::grep", "should complete a draft", "--workers=1").returncode == 0
    npx = run.calls()[-1]
    assert npx.argv == ["playwright", "test", "--grep", "should complete a draft", "--no-deps", "--workers=1"]


def test_playwright_stops_when_there_is_no_slot(run: Runner) -> None:
    result = run("test::pw::headless", exit_code=1)
    assert result.returncode != 0
    assert [c.tool for c in run.calls()] == ["python"]


def test_setup_allocates_before_any_compose_call() -> None:
    assert JUST is not None
    text = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "--dry-run", "test::setup"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    ensure = text.index("scripts.slots --root")
    assert "ensure" in text[ensure : text.index("\n", ensure)]
    assert ensure < text.index("compose down")
    assert "compose --ansi always up -d" in text


def test_release_migrates_and_pulls_before_recreating() -> None:
    assert JUST is not None
    text = subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "--dry-run", "dev::release"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    order = [
        text.index("db::migrate-env release"),
        text.index("docker::release::pull"),
        text.index("compose --stack release down"),
        text.index("compose --stack release up -d"),
    ]
    assert order == sorted(order)
    assert "in-env.sh' release" in text or "in-env.sh release" in text


def _index(calls: list[Call], pred: object) -> int:
    return next(i for i, c in enumerate(calls) if pred(c))  # type: ignore[operator]


def test_dev_up_waits_for_backend_then_syncs_links_and_follows_logs(run: Runner) -> None:
    result = run("dev::up", DF_FAKE_PS_FAILS="1")
    assert result.returncode == 0, result.stderr
    assert "Backend is ready!" in result.stdout
    calls = [c for c in run.calls() if c.tool == "python"]
    dev = [*SLOTS, "--stack", "dev"]
    ps = [i for i, c in enumerate(calls) if c.argv == [*dev, "ps", "backend", "--format", "json"]]
    order = [
        _index(calls, lambda c: c.argv == [*dev, "up", "-d", "--remove-orphans"]),
        ps[0],
        ps[1],
        _index(calls, lambda c: c.argv[: len(dev) + 2] == [*dev, "exec", "-T"] and "requests.get" in c.argv[-1]),
        _index(calls, lambda c: c.argv == ["manage.py", "sync_prod_users"]),
        _index(calls, lambda c: c.argv == ["manage.py", "sync_prod_tournaments"]),
        _index(calls, lambda c: c.argv == ["manage.py", "populate_steam_matches", "--relink-users"]),
        _index(calls, lambda c: c.argv[: len(dev) + 2] == [*dev, "exec", "-T"] and "auto_link_matches_for_tournament" in c.argv[-1]),
        _index(calls, lambda c: c.argv == [*dev, "logs", "-f"]),
    ]
    assert len(ps) == 2 and order == sorted(order)
    steam = calls[order[6]]
    assert steam.test == "false" and steam.cwd == ROOT / "backend"


def test_dev_up_gives_up_waiting_and_still_syncs(run: Runner) -> None:
    result = run("dev::up", DF_BACKEND_WAIT_SECS="0")
    assert result.returncode == 0, result.stderr
    assert "Backend health check timed out, proceeding anyway" in result.stdout
    calls = run.calls()
    assert not any("ps" in c.argv and "backend" in c.argv for c in calls)
    assert calls[-1].argv == [*SLOTS, "--stack", "dev", "logs", "-f"]


def test_setup_stops_cleanly_when_no_slot_is_free(run: Runner) -> None:
    result = run("test::setup", DF_FAKE_ENSURE_FAIL="1")
    assert result.returncode == 1
    assert "all 10 slots are held" in result.stderr
    calls = run.calls()
    assert [c.argv[-1] for c in calls] == ["ensure"]
