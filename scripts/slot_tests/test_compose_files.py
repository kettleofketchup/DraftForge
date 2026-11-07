import pytest

from scripts.slot_tests._helpers import render, render_raw

SLOT3 = {"DF_SUFFIX": "-s3", "DF_HTTPS_PORT": "13443", "DF_BASE_URL": "https://localhost:13443"}


def test_slot_render() -> None:
    cfg = render(["docker-compose.test.yaml", "docker-compose.slot.yaml"], SLOT3)
    s = cfg["services"]
    named = ("frontend", "backend", "redis", "nginx")
    assert {svc: s[svc]["container_name"] for svc in named} == {svc: f"{svc}-s3" for svc in named}
    for svc in ("celery-worker", "celery-beat", "discord-bot"):
        assert "container_name" not in s[svc], svc
    assert [(p["published"], p["target"]) for p in s["nginx"]["ports"]] == [("13443", 443)]
    assert s["frontend"]["environment"]["DF_HTTPS_PORT"] == "13443"
    for svc in ["backend", "celery-worker", "celery-beat", "discord-bot"]:
        assert s[svc]["environment"]["SITE_URL"] == "https://localhost:13443"
    assert s["backend"]["environment"]["OTEL_SERVICE_NAME"] == "backend"
    assert s["backend"]["environment"]["DF_EXTRA_CSRF_ORIGINS"] == "https://localhost:13443"
    assert s["redis"]["volumes"][0]["source"].endswith("backend/.redis_data-s3")
    assert s["celery-beat"]["command"][-1] == "/app/backend/celerybeat-schedule-s3"


def test_offline_blanks_tokens() -> None:
    s = render(
        ["docker-compose.test.yaml", "docker-compose.slot.yaml", "docker-compose.slot-offline.yaml"], SLOT3
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


def test_slot_file_requires_helper_env() -> None:
    r = render_raw(["docker-compose.test.yaml", "docker-compose.slot.yaml"], {})
    assert r.returncode != 0 and "run via scripts.slots" in r.stderr


def test_base_test_file_invariants() -> None:
    cfg = render(["docker-compose.test.yaml"], {}, project=None)
    assert cfg["name"] == "df"
    ports = sorted((str(p["published"]), p["target"]) for p in cfg["services"]["nginx"]["ports"])
    assert ports == [("443", 443), ("80", 80)]
    names = {s["container_name"] for s in cfg["services"].values() if "container_name" in s}
    assert names <= {"frontend", "backend", "redis", "nginx"}


@pytest.mark.parametrize("f", ["docker-compose.debug.yaml", "docker-compose.debug.m1.yaml"])
def test_dev_render(f: str) -> None:
    cfg = render([f], {}, project=None)
    assert cfg["name"] == "df-dev"
    names = {s["container_name"] for s in cfg["services"].values() if "container_name" in s}
    assert names <= {"frontend-dev", "backend-dev", "redis-dev", "nginx-dev"}
    assert cfg["services"]["redis"]["volumes"][0]["source"].endswith("backend/.redis_data-dev")
    if "celery-beat" in cfg["services"]:
        assert cfg["services"]["celery-beat"]["command"][-1] == "/app/backend/celerybeat-schedule-dev"
    assert sorted(p["published"] for p in cfg["services"]["nginx"]["ports"]) == ["443", "80"]
