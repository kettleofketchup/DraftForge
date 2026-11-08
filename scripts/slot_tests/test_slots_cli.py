from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import scripts.slots as slots
from scripts.slot_tests._helpers import FakeHost
from scripts.slots import SLOT_FILE_REL, TRANSITION_WARNING

Execs = list[tuple[list[str], dict[str, str]]]


@pytest.fixture
def cli(
    monkeypatch: pytest.MonkeyPatch,
    fake_host: FakeHost,
    make_worktree: Callable[[str], Path],
) -> tuple[Path, Execs]:
    root = make_worktree("a")
    execs: Execs = []
    monkeypatch.setattr(slots, "MODULE_ROOT", root)
    monkeypatch.setattr(slots, "REAL_HOST", fake_host)
    monkeypatch.setattr(slots, "_toplevel", lambda cwd: root)
    monkeypatch.setattr(
        slots.os, "execvpe", lambda f, argv, env: execs.append((list(argv), dict(env)))
    )

    def no_run(*a: Any, **k: Any) -> int:
        raise AssertionError("run_one_off must not be reached")

    monkeypatch.setattr(slots, "run_one_off", no_run)
    return root, execs


def test_cli_refuses_mismatched_root(
    cli: tuple[Path, Execs], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root, execs = cli
    assert slots.main(["--root", str(tmp_path / "elsewhere"), "compose", "config"]) == 2
    assert "is not this checkout" in capsys.readouterr().err and execs == []


def test_cli_refuses_cwd_in_other_checkout(
    cli: tuple[Path, Execs],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, execs = cli
    elsewhere = tmp_path / "other-checkout"
    elsewhere.mkdir()
    monkeypatch.setattr(slots, "_toplevel", lambda cwd: elsewhere.resolve())
    assert slots.main(["--root", str(root), "compose", "down"]) == 2
    assert "is not this checkout" in capsys.readouterr().err and execs == []


def test_cli_as_slot_0_only_with_config(
    cli: tuple[Path, Execs], capsys: pytest.CaptureFixture[str]
) -> None:
    root, execs = cli
    assert slots.main(["--root", str(root), "compose", "--as-slot", "0", "up"]) == 2
    assert (
        "--as-slot 0 is only allowed with config" in capsys.readouterr().err
        and execs == []
    )


def test_cli_as_slot_0_config_execs_df_with_merged_env(
    cli: tuple[Path, Execs], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, execs = cli
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/podman.sock")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "stale")
    slots.main(["--root", str(root), "compose", "--as-slot", "0", "config"])
    ((argv, env),) = execs
    assert argv[argv.index("-p") + 1] == "df" and argv[-1] == "config"
    assert (
        env["PATH"]
        and env["DOCKER_HOST"] == "unix:///run/podman.sock"
        and env["COMPOSE_PROJECT_NAME"] == "df"
    )
    assert not (root / SLOT_FILE_REL).exists()


def test_cli_compose_down_without_slot_never_execs(
    cli: tuple[Path, Execs], capsys: pytest.CaptureFixture[str]
) -> None:
    root, execs = cli
    assert slots.main(["--root", str(root), "compose", "down"]) == 1
    assert "just test::slot" in capsys.readouterr().err and execs == []


def test_cli_compose_run_goes_to_run_one_off(
    cli: tuple[Path, Execs], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, execs = cli
    got: list[list[str]] = []
    monkeypatch.setattr(
        slots, "run_one_off", lambda args, **k: got.append(list(args)) or 7
    )
    assert (
        slots.main(["--root", str(root), "compose", "run", "--rm", "backend", "true"])
        == 7
    )
    assert got == [["--rm", "backend", "true"]] and execs == []


def test_cli_compose_stack_dev(cli: tuple[Path, Execs]) -> None:
    root, execs = cli
    assert slots.main(["--root", str(root), "compose", "--stack", "dev", "ps"]) == 0
    ((argv, _),) = execs
    assert argv[argv.index("-p") + 1] == "df-dev"


def test_cli_status_writes_nothing(
    cli: tuple[Path, Execs], fake_host: FakeHost
) -> None:
    root, _ = cli
    assert slots.main(["--root", str(root), "status"]) == 0
    assert fake_host.calls != []
    assert (
        not (fake_host.common / "df-slots").exists()
        and not (root / SLOT_FILE_REL).exists()
    )


def test_cli_print_allocates_and_warns(
    cli: tuple[Path, Execs],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = cli
    monkeypatch.setenv("DF_SLOT", "2")
    assert slots.main(["--root", str(root), "print"]) == 0
    out = capsys.readouterr()
    assert "DF_SLOT=2" in out.out and out.out.rstrip().endswith(TRANSITION_WARNING)
    assert (root / SLOT_FILE_REL).exists()


def test_cli_slot_error_exits_1(
    cli: tuple[Path, Execs], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = cli
    assert slots.main(["--root", str(root), "reap", "postgres"]) == 1
    assert "refusing to reap" in capsys.readouterr().err


@pytest.mark.parametrize(
    "opts",
    [
        ["-p", "df"],
        ["--project-name", "df"],
        ["--project-name=df"],
        ["-pdf"],
        ["-p=df"],
        ["--project-directory", "/tmp/elsewhere"],
        ["--project-directory=/tmp/elsewhere"],
        ["-f", "/tmp/c.yaml"],
        ["--file=/tmp/c.yaml"],
        ["-fc.yaml"],
        ["--ansi", "never", "-p", "df"],
    ],
)
@pytest.mark.parametrize("stack", [[], ["--stack", "dev"], ["--stack", "prod"]])
def test_cli_compose_refuses_project_override(
    cli: tuple[Path, Execs],
    fake_host: FakeHost,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    opts: list[str],
    stack: list[str],
) -> None:
    root, execs = cli
    monkeypatch.setenv("DF_SLOT", "3")
    slots.ensure_slot(root, fake_host)
    assert slots.main(["--root", str(root), "compose", *stack, *opts, "down"]) == 1
    assert "not allowed" in capsys.readouterr().err
    assert execs == [] and fake_host.compose_calls == []


def test_cli_as_slot_0_config_refuses_project_override(
    cli: tuple[Path, Execs], capsys: pytest.CaptureFixture[str]
) -> None:
    root, execs = cli
    argv = ["--root", str(root), "compose", "--as-slot", "0", "-p", "x", "config"]
    assert slots.main(argv) == 1
    assert "not allowed" in capsys.readouterr().err and execs == []
