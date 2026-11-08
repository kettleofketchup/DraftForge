"""Playwright base URL and Redis flush for the test stack.

CLI (from the repo root, used by just/test/pw.just and scripts/demo.py):
    python -m scripts.compose env          # print `export DF_BASE_URL=...` lines
    python -m scripts.compose flush-redis  # FLUSHALL the test stack's Redis
"""

from __future__ import annotations

import argparse
import os
import shlex
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.slots import SlotError, prepare, read_slot

FLUSH_ARGS = ("exec", "-T", "redis", "redis-cli", "FLUSHALL")


def in_container(root: Path = Path("/")) -> bool:
    if (root / ".dockerenv").exists() or (root / "run/.containerenv").exists():
        return True
    try:
        return "docker" in (root / "proc/1/cgroup").read_text()
    except OSError:
        return False


def playwright_env() -> dict[str, str]:
    if in_container():
        return {
            "DF_BASE_URL": "https://nginx",
            "DF_BASE_URL_SOURCE": "container",
        }
    return {
        "DF_BASE_URL": read_slot().base_url,
        "DF_BASE_URL_SOURCE": "runner",
    }


def base_url() -> str:
    return playwright_env()["DF_BASE_URL"]


def flush_test_redis() -> None:
    print("Flushing Redis cache...")
    if in_container():
        _flush_redis_service()
        return
    argv, env = prepare("test", FLUSH_ARGS)
    subprocess.run(
        argv, env={**os.environ, **env}, check=True, stdout=subprocess.DEVNULL
    )


def _flush_redis_service(host: str = "redis", port: int = 6379) -> None:
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(b"*1\r\n$8\r\nFLUSHALL\r\n")
            reply = sock.recv(64)
    except OSError as exc:
        print(
            f"warning: redis FLUSHALL via {host}:{port} failed: {exc}", file=sys.stderr
        )
        return
    if not reply.startswith(b"+OK"):
        print(
            f"warning: redis FLUSHALL via {host}:{port} replied {reply!r}",
            file=sys.stderr,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.compose")
    parser.add_argument("cmd", choices=["env", "flush-redis"])
    ns = parser.parse_args(argv)
    try:
        if ns.cmd == "env":
            for key, value in playwright_env().items():
                print(f"export {key}={shlex.quote(value)}")
        else:
            flush_test_redis()
    except SlotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"redis FLUSHALL failed (exit {exc.returncode})", file=sys.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
