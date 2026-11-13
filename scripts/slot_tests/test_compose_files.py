import re
import shutil
from pathlib import Path

import pytest

from scripts.slot_tests._helpers import ROOT, render, render_raw

SLOT3 = {
    "DF_SUFFIX": "-s3",
    "DF_HTTPS_PORT": "13443",
    "DF_BASE_URL": "https://localhost:13443",
}


def test_slot_render() -> None:
    cfg = render(["docker-compose.test.yaml", "docker-compose.slot.yaml"], SLOT3)
    s = cfg["services"]
    named = ("frontend", "backend", "redis", "nginx")
    assert {svc: s[svc]["container_name"] for svc in named} == {
        svc: f"{svc}-s3" for svc in named
    }
    for svc in ("celery-worker", "celery-beat", "discord-bot"):
        assert "container_name" not in s[svc], svc
    assert [(p["published"], p["target"]) for p in s["nginx"]["ports"]] == [
        ("13443", 443)
    ]
    assert s["frontend"]["environment"]["DF_HTTPS_PORT"] == "13443"
    for svc in ["backend", "celery-worker", "celery-beat", "discord-bot"]:
        assert s[svc]["environment"]["SITE_URL"] == "https://localhost:13443"
    assert s["backend"]["environment"]["OTEL_SERVICE_NAME"] == "backend"
    assert (
        s["backend"]["environment"]["DF_EXTRA_CSRF_ORIGINS"]
        == "https://localhost:13443"
    )
    assert s["backend"]["environment"]["DF_SESSION_COOKIE_NAME"] == "sessionid-s3"
    assert s["backend"]["environment"]["DF_CSRF_COOKIE_NAME"] == "csrftoken-s3"
    assert s["frontend"]["environment"]["VITE_CSRF_COOKIE_NAME"] == "csrftoken-s3"
    assert [(v["type"], v["source"]) for v in s["redis"]["volumes"]] == [
        ("volume", "redis_data")
    ]
    assert s["celery-beat"]["command"][-1] == "/app/backend/celerybeat-schedule-s3"


def test_offline_blanks_tokens() -> None:
    s = render(
        [
            "docker-compose.test.yaml",
            "docker-compose.slot.yaml",
            "docker-compose.slot-offline.yaml",
        ],
        SLOT3,
    )["services"]
    for svc in ["backend", "celery-worker", "discord-bot", "celery-beat"]:
        env = s[svc]["environment"]
        assert (env["DISCORD_BOT_TOKEN"], env["STEAM_API_KEY"]) == ("", ""), svc


def test_run_redis_tmpfs() -> None:
    r = render(
        [
            "docker-compose.test.yaml",
            "docker-compose.slot.yaml",
            "docker-compose.slot-offline.yaml",
            "docker-compose.run.yaml",
        ],
        SLOT3,
    )["services"]["redis"]
    assert r.get("volumes", []) == [] and r["tmpfs"] == ["/data"]


@pytest.mark.parametrize(
    ("files", "env", "project"),
    [
        (["docker-compose.test.yaml"], {}, "df"),
        (["docker-compose.test.yaml", "docker-compose.slot.yaml"], SLOT3, "df-s3"),
    ],
)
def test_redis_definition_is_worktree_independent(
    files: list[str], env: dict[str, str], project: str, tmp_path: Path
) -> None:
    (tmp_path / "docker").mkdir()
    shutil.copy(ROOT / "docker" / ".env.test", tmp_path / "docker" / ".env.test")
    here = render(files, env, project=project)
    there = render(files, env, project=project, project_dir=tmp_path)
    assert here["services"]["redis"] == there["services"]["redis"]
    assert here["volumes"]["redis_data"]["name"] == f"{project}_redis_data"


def test_slot_file_requires_helper_env() -> None:
    r = render_raw(["docker-compose.test.yaml", "docker-compose.slot.yaml"], {})
    assert r.returncode != 0 and "run via scripts.slots" in r.stderr


def test_base_test_file_invariants() -> None:
    cfg = render(["docker-compose.test.yaml"], {}, project=None)
    assert cfg["name"] == "df"
    ports = sorted(
        (str(p["published"]), p["target"]) for p in cfg["services"]["nginx"]["ports"]
    )
    assert ports == [("443", 443), ("80", 80)]
    names = {
        s["container_name"] for s in cfg["services"].values() if "container_name" in s
    }
    assert names <= {"frontend", "backend", "redis", "nginx"}
    for svc in ("frontend", "backend"):
        env = cfg["services"][svc].get("environment") or {}
        assert not {"DF_SESSION_COOKIE_NAME", "DF_CSRF_COOKIE_NAME", "VITE_CSRF_COOKIE_NAME"} & set(env), svc


@pytest.mark.parametrize(
    "f", ["docker-compose.debug.yaml", "docker-compose.debug.m1.yaml"]
)
def test_dev_render(f: str) -> None:
    cfg = render([f], {}, project=None)
    assert cfg["name"] == "df-dev"
    names = {
        s["container_name"] for s in cfg["services"].values() if "container_name" in s
    }
    assert names <= {"frontend-dev", "backend-dev", "redis-dev", "nginx-dev"}
    assert cfg["services"]["redis"]["volumes"][0]["source"].endswith(
        "backend/.redis_data-dev"
    )
    if "celery-beat" in cfg["services"]:
        assert (
            cfg["services"]["celery-beat"]["command"][-1]
            == "/app/backend/celerybeat-schedule-dev"
        )
    assert sorted(p["published"] for p in cfg["services"]["nginx"]["ports"]) == [
        "443",
        "80",
    ]


DOTA_LOBBY_PROFILE = {"COMPOSE_PROFILES": "dota-lobby"}


def test_dota_lobby_simulator_is_behind_a_profile() -> None:
    # Off by default: CI and plain `test::up` never pull the simulator image.
    for files, env in (
        (["docker-compose.test.yaml"], {}),
        (["docker-compose.test.yaml", "docker-compose.slot.yaml"], SLOT3),
    ):
        assert "dota-lobby" not in render(files, env)["services"]


@pytest.mark.parametrize(
    ("env", "image"),
    [
        ({}, "ghcr.io/kettleofketchup/dota_lobby:0.2.0"),
        ({"DOTA_LOBBY_IMAGE_TAG": "1.4.0"}, "ghcr.io/kettleofketchup/dota_lobby:1.4.0"),
        (
            {"DOTA_LOBBY_IMAGE": "ghcr.io/kettleofketchup/dota_lobby:local"},
            "ghcr.io/kettleofketchup/dota_lobby:local",
        ),
    ],
)
def test_dota_lobby_simulator_render(env: dict[str, str], image: str) -> None:
    cfg = render(
        ["docker-compose.test.yaml", "docker-compose.slot.yaml"],
        SLOT3 | DOTA_LOBBY_PROFILE | env,
    )
    svc = cfg["services"]["dota-lobby"]
    assert svc["image"] == image
    assert svc["command"] == ["serve", "--simulate"]
    assert svc["profiles"] == ["dota-lobby"]
    # Project-scoped name, so every slot runs its own simulator.
    assert "container_name" not in svc
    assert "ports" not in svc
    assert [v["target"] for v in svc["volumes"]] == [
        "/app/config/config.yaml",
        "/app/config/secrets.yaml",
    ]
    assert all(v["read_only"] for v in svc["volumes"])
    assert svc["tmpfs"] == ["/app/state:mode=1777"]
    assert svc["environment"]["DOTA_LOBBY_SECRETS_FILE"] == "/app/config/secrets.yaml"


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key] = value.strip().strip('"')
    return out


def test_dota_lobby_simulator_matches_the_test_env() -> None:
    import yaml

    env = _env_file(ROOT / "docker" / ".env.test")
    sim_dir = ROOT / "docker" / "dota-lobby"
    config = yaml.safe_load((sim_dir / "simulator.yaml").read_text())
    secrets = yaml.safe_load((sim_dir / "simulator-secrets.yaml").read_text())[
        "secrets"
    ]
    [hook] = config["webhooks"]
    assert env["DOTA_LOBBY_ENABLED"] == "true"
    assert env["DOTA_LOBBY_URL"] == "http://dota-lobby:8080"
    assert secrets["api_key"] == env["DOTA_LOBBY_API_KEY"]
    assert hook["url"] == "http://backend:8000/api/internal/lobbies/events/"
    assert hook["token_header"] == "X-Internal-Token"
    assert secrets["webhook_secrets"] == {hook["url"]: env["DOTA_LOBBY_WEBHOOK_SECRET"]}
    assert secrets["webhook_tokens"] == {hook["url"]: env["INTERNAL_SERVICE_TOKEN"]}
    assert config["simulation"]["enabled"] is True
    # Simulation mode refuses bots with Steam credentials.
    assert all(set(bot) <= {"name", "leagues"} for bot in config["bots"])
    # The bots administer the league the dota_lobby test data uses.
    data = (ROOT / "backend" / "tests" / "data" / "dota_lobby.py").read_text()
    league = int(re.search(r"^LOBBY_STEAM_LEAGUE_ID = (\d+)$", data, re.M).group(1))
    assert all(bot["leagues"] == [league] for bot in config["bots"])
