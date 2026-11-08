"""Container runtime detection, used by settings to pick the Redis host."""

from pathlib import Path

# /.dockerenv is written by Docker, /run/.containerenv by podman.
MARKER_FILES: tuple[str, ...] = (".dockerenv", "run/.containerenv")
# cgroup v1 paths; under cgroup v2 a container's /proc/1/cgroup is just "0::/".
CGROUP_HINTS: tuple[str, ...] = ("docker", "libpod")


def in_container(root: Path = Path("/")) -> bool:
    if any((root / marker).exists() for marker in MARKER_FILES):
        return True
    try:
        cgroup = (root / "proc/1/cgroup").read_text()
    except OSError:
        return False
    return any(hint in cgroup for hint in CGROUP_HINTS)
