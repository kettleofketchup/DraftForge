import itertools
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.slots import ContainerOwner

ROOT = Path(__file__).resolve().parents[2]
ROOTX = Path("/x/wt")
REG = Path("/x/git-common/df-slots")


def owner(
    *,
    name: str = "c",
    project: str = "df",
    service: str = "nginx",
    wd: Path | None = None,
    running: bool = True,
    config_files: tuple[str, ...] = ("/x/docker/docker-compose.test.yaml",),
    oneoff: bool = False,
) -> ContainerOwner:
    return ContainerOwner(
        name=name,
        running=running,
        project=project,
        service=service,
        working_dir=wd,
        config_files=config_files,
        oneoff=oneoff,
    )


def reserve(reg: Path, n: int, owner_path: Path, token: str, last_used: int) -> None:
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"slot-{n}").write_text(f"owner={owner_path}\ntoken={token}\nlast_used={last_used}\n")


class FakeHost:
    def __init__(self, common: Path, worktrees: set[Path] | None = None) -> None:
        self.ports_busy: set[int] = set()
        self.projects: dict[str, list[ContainerOwner]] = {}
        self.worktrees: set[Path] = set(worktrees or ())
        self.clock_value: list[float] = [1_000_000.0]
        self.calls: list[str] = []
        self.probed_ports: list[int] = []
        self.compose_calls: list[list[str]] = []
        self.run_envs: list[dict[str, str]] = []
        self.run_outputs: list[tuple[int, str]] = []
        self.common = common
        self._tok = itertools.count()

    def port_busy(self, port: int) -> bool:
        self.calls.append("port_busy")
        self.probed_ports.append(port)
        return port in self.ports_busy

    def containers(self, project: str) -> list[ContainerOwner]:
        self.calls.append("containers")
        return list(self.projects.get(project, []))

    def service_containers(self, service: str) -> list[ContainerOwner]:
        self.calls.append("service_containers")
        return [o for os_ in self.projects.values() for o in os_ if o.service == service and o.running]

    def all_df_containers(self) -> list[ContainerOwner]:
        self.calls.append("all_df_containers")
        return [o for os_ in self.projects.values() for o in os_]

    def common_dir(self, root: Path) -> Path:
        self.calls.append("common_dir")
        return self.common

    def live_worktrees(self, root: Path) -> set[Path]:
        self.calls.append("live_worktrees")
        return set(self.worktrees)

    def run(self, argv: list[str], env: dict[str, str], capture: bool) -> tuple[int, str]:
        self.calls.append("run")
        self.compose_calls.append(list(argv))
        self.run_envs.append(dict(env))
        return self.run_outputs.pop(0) if self.run_outputs else (0, "")

    def clock(self) -> float:
        return self.clock_value[0]

    def new_token(self) -> str:
        return f"tok{next(self._tok)}"


def render_raw(
    files: list[str], env: dict[str, str], *, project: str | None = "df-s3"
) -> subprocess.CompletedProcess[str]:
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        pytest.skip("docker compose unavailable")
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DF_", "COMPOSE_"))} | env
    argv = ["docker", "compose", "--project-directory", str(ROOT)]
    argv += ["-p", project] if project else []
    argv += [a for f in files for a in ("-f", str(ROOT / "docker" / f))]
    return subprocess.run([*argv, "config", "--format", "json"], env=clean, capture_output=True, text=True)


def render(files: list[str], env: dict[str, str], *, project: str | None = "df-s3") -> dict:
    r = render_raw(files, env, project=project)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)
