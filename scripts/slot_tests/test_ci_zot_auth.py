"""ci::zot-auth writes the plain-HTTP Zot registry's auth entry into the docker client config."""

import base64
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")
ZOT = "zot.zot.svc.cluster.local:5000"
PASSWORD = "s3cret-zot-pass"

pytestmark = pytest.mark.skipif(JUST is None, reason="just is not on PATH")


def zot_auth(
    tmp_path: Path, password: str = PASSWORD
) -> subprocess.CompletedProcess[str]:
    assert JUST is not None
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ZOT_PASSWORD", "DOCKER_CONFIG")
    }
    env |= {"ZOT_PASSWORD": password, "DOCKER_CONFIG": str(tmp_path / "docker")}
    return subprocess.run(
        [JUST, "--justfile", str(ROOT / "justfile"), "ci::zot-auth"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def config(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "docker" / "config.json").read_text())


def encoded() -> str:
    return base64.b64encode(f"ci:{PASSWORD}".encode()).decode()


def test_zot_auth_writes_entry(tmp_path: Path) -> None:
    r = zot_auth(tmp_path)
    assert r.returncode == 0, r.stderr
    assert config(tmp_path)["auths"][ZOT] == {"auth": encoded()}


def test_zot_auth_keeps_existing_auths(tmp_path: Path) -> None:
    (tmp_path / "docker").mkdir()
    existing = {
        "auths": {"ghcr.io": {"auth": "Z2hjcjp0b2tlbg=="}},
        "credsStore": "",
        "currentContext": "default",
    }
    (tmp_path / "docker" / "config.json").write_text(json.dumps(existing))
    r = zot_auth(tmp_path)
    assert r.returncode == 0, r.stderr
    cfg = config(tmp_path)
    assert cfg["auths"]["ghcr.io"] == {"auth": "Z2hjcjp0b2tlbg=="}
    assert cfg["auths"][ZOT] == {"auth": encoded()}
    assert cfg["currentContext"] == "default"
    assert cfg["credsStore"] == ""


def test_zot_auth_file_mode_600(tmp_path: Path) -> None:
    r = zot_auth(tmp_path)
    assert r.returncode == 0, r.stderr
    mode = stat.S_IMODE((tmp_path / "docker" / "config.json").stat().st_mode)
    assert mode == 0o600


def test_zot_auth_masks_encoded_value(tmp_path: Path) -> None:
    r = zot_auth(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"::add-mask::{encoded()}\n"
    assert PASSWORD not in r.stdout + r.stderr


def test_zot_auth_requires_password(tmp_path: Path) -> None:
    r = zot_auth(tmp_path, password="")
    assert r.returncode != 0
    assert not (tmp_path / "docker" / "config.json").exists()
