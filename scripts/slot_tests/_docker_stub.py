"""A recording `docker` stub for recipe tests that pull, inspect or tag images."""

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")

DOCKER = "Docker version 27.3.1, build ce12230"
PODMAN = "podman version 6.1.4"

# One record per call: the argv joined by NUL, then a newline. A single O_APPEND
# write keeps records whole when recipes run docker in parallel.
_STUB = """#!{python} -I
import os, sys
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print({version!r})
    sys.exit(0)
record = "".join(a + "\\0" for a in args) + "\\n"
fd = os.open({log!r}, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
os.write(fd, record.encode())
os.close(fd)
ref = next((a for a in reversed(args) if not a.startswith("-")), "")
with open({existing!r}) as f:
    present = ref in f.read().splitlines()
if args[:1] == ["pull"]:
    if {fail_pull!r} or not present:
        sys.exit(1)
    with open({existing!r}, "a") as f:
        f.write(ref + "\\n")
    sys.exit(0)
if args[:3] == ["buildx", "imagetools", "inspect"] or args[:2] == ["image", "inspect"]:
    sys.exit(0 if present else 1)
sys.exit(0)
"""


def docker_stub(
    tmp_path: Path,
    version: str = DOCKER,
    existing: Iterable[str] = frozenset(),
    fail_pull: bool = False,
) -> tuple[dict[str, str], Path]:
    """Put a recording docker first on PATH; return (env, call log path).

    `pull`, `buildx imagetools inspect` and `image inspect` succeed only for a ref
    (the last non-flag argument) in `existing`; `pull` always fails with
    `fail_pull`. A pulled ref is recorded as present locally. Every other
    command exits 0.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "docker-calls"
    log.touch()
    state = tmp_path / "docker-existing"
    state.write_text("".join(f"{ref}\n" for ref in existing))
    stub = bin_dir / "docker"
    stub.write_text(
        _STUB.format(
            python=sys.executable,
            version=version,
            log=str(log),
            existing=str(state),
            fail_pull=fail_pull,
        )
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return env, log


def run_just(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    assert JUST is not None
    return subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def calls(log: Path) -> list[list[str]]:
    """The recorded docker calls, each as its argv."""
    return [record.split("\0")[:-1] for record in log.read_text().split("\n") if record]
