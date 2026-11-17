"""Redis host resolution shared by `backend.settings` and `config.settings_celery`.

The web, worker, beat and Discord bot processes must reach the same Redis, so
both settings modules resolve `REDIS_HOST` here: an unset or blank value falls
back to the compose service name inside a container and to localhost outside.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Mapping
from pathlib import Path


@functools.lru_cache(maxsize=1)
def is_docker(root: Path = Path("/")) -> bool:
    """Check if running inside a Docker or podman container."""
    if (root / ".dockerenv").exists() or (root / "run/.containerenv").exists():
        return True
    try:
        return "docker" in (root / "proc/1/cgroup").read_text()
    except Exception:
        return False


def resolve_redis_host(
    environ: Mapping[str, str] | None = None, *, in_docker: bool | None = None
) -> str:
    env = os.environ if environ is None else environ
    host = env.get("REDIS_HOST", "").strip()
    if host:
        return host
    if in_docker is None:
        in_docker = is_docker()
    return "redis" if in_docker else "localhost"
