from __future__ import annotations

import shlex
import sys
from pathlib import Path

from invoke.context import Context
from invoke.exceptions import Exit
from invoke.runners import Result

from scripts.slots import SlotEnv, SlotError, Stack, prepare, read_slot, run_one_off


def _fail(exc: SlotError) -> Exit:
    print(str(exc), file=sys.stderr)
    return Exit(code=1)


def run_compose(
    c: Context,
    stack: Stack,
    *args: str,
    pty: bool = False,
    warn: bool = False,
    hide: bool = False,
    slot: SlotEnv | None = None,
) -> Result | None:
    try:
        argv, env = prepare(stack, args, slot=slot)
    except SlotError as exc:
        raise _fail(exc) from exc
    return c.run(shlex.join(argv), env=env, pty=pty, warn=warn, hide=hide)


def run_compose_one_off(
    c: Context, stack: Stack, service: str, cmd: str, entrypoint: str | None = None
) -> None:
    args = [
        "--rm",
        *(["--entrypoint", entrypoint] if entrypoint is not None else []),
        service,
        *shlex.split(cmd),
    ]
    if stack != "test":
        run_compose(c, stack, "run", *args, pty=True)
        return
    try:
        code = run_one_off(args)
    except SlotError as exc:
        raise _fail(exc) from exc
    if code != 0:
        raise Exit(code=code)


def in_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        return "docker" in Path("/proc/1/cgroup").read_text()
    except OSError:
        return False


def playwright_env() -> dict[str, str]:
    if in_container():
        return {
            "DF_BASE_URL": "https://nginx",
            "DF_BASE_URL_SOURCE": "container",
            "DOCKER_HOST": "nginx",
        }
    try:
        base_url = read_slot().base_url
    except SlotError as exc:
        raise _fail(exc) from exc
    return {
        "DF_BASE_URL": base_url,
        "DF_BASE_URL_SOURCE": "invoke",
        "DOCKER_HOST": "localhost",
    }


def base_url() -> str:
    return playwright_env()["DF_BASE_URL"]
