import time
from typing import cast

import invoke
from dotenv import load_dotenv
from invoke.collection import Collection
from invoke.context import Context
from invoke.exceptions import Exit
from invoke.tasks import task
from rich.traceback import install

import paths
from backend.tasks import db_migrate, db_populate_steam, ns_db
from scripts.compose import _fail, run_compose, run_compose_one_off, shell_argv
from scripts.docker import docker_release_pull, ns_docker
from scripts.docs import ns_docs
from scripts.slots import STACKS, SlotError, Stack
from scripts.sync_version import (
    get_version_from_env,
)
from scripts.tests import dev_test, ns_demo, ns_test
from scripts.update import ns_update
from scripts.version import ns_version

config = None
version = None

install(suppress=[invoke])

ns = Collection()
ns_dev = Collection("dev")
ns_prod = Collection("prod")
ns.add_collection(ns_prod, "prod")
ns.add_collection(ns_test, "test")
ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")
ns.add_collection(ns_db, "db")
ns.add_collection(ns_update, "update")
ns.add_collection(ns_version, "version")
ns.add_collection(ns_docs, "docs")
ns.add_collection(ns_demo, "demo")


def docker_compose_down(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "down", "--remove-orphans")


def docker_compose_up(c: Context, stack: Stack, detach: bool = False) -> None:
    run_compose(c, stack, "up", *(["-d"] if detach else []), "--remove-orphans")


def docker_compose_logs(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "logs", "-f")


def docker_compose_ps(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "ps")


def docker_compose_restart(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "restart")


def docker_compose_stop(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "stop")


def docker_compose_build(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "build")


def docker_compose_pull(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "pull")


def docker_compose_top(c: Context, stack: Stack) -> None:
    run_compose(c, stack, "top")


def docker_compose_exec(c: Context, stack: Stack, service: str, cmd_str: str) -> None:
    run_compose(c, stack, "exec", service, *shell_argv(cmd_str), pty=True)


def docker_compose_run(
    c: Context, stack: Stack, service: str, cmd_str: str, entrypoint: str | None = None
) -> None:
    """Run a one-off command in a new container with --rm flag.

    Pass ``entrypoint=""`` to bypass the image entrypoint (e.g. daphne) so the
    command runs directly — required for ``python manage.py ...`` one-offs.
    """
    run_compose_one_off(c, stack, service, cmd_str, entrypoint=entrypoint)


HEALTH_CHECK_CODE = (
    "import requests; requests.get('http://localhost:8000/api/', timeout=5)"
)
AUTO_LINK_CODE = (
    "import django; django.setup(); "
    "from app.models import Tournament; "
    "from steam.functions.game_linking import auto_link_matches_for_tournament; "
    "results = [auto_link_matches_for_tournament(t.id) for t in Tournament.objects.all()]; "
    "linked = sum(r['auto_linked_count'] for r in results); "
    "suggestions = sum(r['suggestions_created_count'] for r in results); "
    "print(f'Auto-linked {linked} games, created {suggestions} suggestions')"
)


def _backend_healthy(c: Context, stack: Stack) -> bool:
    result = run_compose(
        c, stack, "ps", "backend", "--format", "json", hide=True, warn=True
    )
    if result is None or not result.ok or "running" not in result.stdout.lower():
        return False
    health_result = run_compose(
        c,
        stack,
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        HEALTH_CHECK_CODE,
        hide=True,
        warn=True,
    )
    return health_result is not None and health_result.ok


def _wait_for_backend(c: Context, stack: Stack, timeout: int = 120) -> bool:
    """Wait for backend container to be healthy and accepting requests."""
    print("Waiting for backend to be ready...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if _backend_healthy(c, stack):
                print("Backend is ready!")
                return True
        except (SlotError, Exit):
            pass
        time.sleep(2)

    print("Warning: Backend health check timed out, proceeding anyway...")
    return False


def _auto_link_all_tournaments(c: Context, stack: Stack) -> None:
    """Run auto-link for all tournaments to link games to Steam matches."""
    print("Auto-linking tournament games to Steam matches...")
    run_compose(
        c, stack, "exec", "-T", "backend", "python", "-c", AUTO_LINK_CODE, warn=True
    )


@task
def dev_debug(c: Context) -> None:
    db_migrate(c, paths.DEBUG_ENV_FILE)
    load_dotenv(paths.DEBUG_ENV_FILE)
    run_compose(
        c, "dev", "--ansi", "always", "up", "--no-attach", "nginx", "--remove-orphans"
    )


@task
def dev_live(c: Context) -> None:
    cmd = "./scripts/tmux.sh"
    c.run(cmd, pty=True)


@task
def dev_prod(c: Context) -> None:
    with c.cd(paths.PROJECT_PATH):
        load_dotenv(paths.PROD_ENV_FILE)
        db_migrate(c, paths.PROD_ENV_FILE)
    run_compose(c, "prod", "up")


@task
def dev_mac(c: Context) -> None:
    db_migrate(c, paths.DEBUG_ENV_FILE)
    load_dotenv(paths.DEBUG_ENV_FILE)
    run_compose(
        c,
        "dev-m1",
        "--ansi",
        "always",
        "up",
        "--no-attach",
        "nginx",
        "--remove-orphans",
    )


@task
def dev_release(c: Context) -> None:
    # Read VERSION from .env.release and set it as environment variable
    with c.cd(paths.PROJECT_PATH):
        load_dotenv(paths.RELEASE_ENV_FILE)
        db_migrate(c, paths.RELEASE_ENV_FILE)
        docker_release_pull(c)

        version = get_version_from_env(paths.RELEASE_ENV_FILE.resolve())
        print(f"launching release version {version}")
        run_compose(c, "release", "down")
        run_compose(c, "release", "up", "-d")


ns_dev.add_task(dev_live, "live")
ns_dev.add_task(dev_debug, "debug")
ns_dev.add_task(dev_test, "test")

ns_dev.add_task(dev_mac, "mac")

ns_dev.add_task(dev_prod, "prod")
ns_dev.add_task(dev_release, "release")


# =============================================================================
# Environment Tasks: dev, test, prod
# =============================================================================


# Sync from production tasks (defined before dev_up since it depends on them)
@task
def dev_sync_users(c: Context, dry_run: bool = False) -> None:
    """Sync users from production (dota.kettle.sh) to local dev database."""
    load_dotenv(paths.DEBUG_ENV_FILE)
    db_migrate(c, paths.DEBUG_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        flags = "--dry-run" if dry_run else ""
        cmd = f"DISABLE_CACHE=true python manage.py sync_prod_users {flags}"
        c.run(cmd, pty=True)


@task
def dev_sync_tournaments(c: Context, dry_run: bool = False) -> None:
    """Sync tournaments from production (dota.kettle.sh) to local dev database."""
    load_dotenv(paths.DEBUG_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        flags = "--dry-run" if dry_run else ""
        cmd = f"DISABLE_CACHE=true python manage.py sync_prod_tournaments {flags}"
        c.run(cmd, pty=True)


@task
def dev_sync_all(c: Context, dry_run: bool = False) -> None:
    """Sync all data (users, tournaments) from production to local dev database."""
    dev_sync_users(c, dry_run=dry_run)
    dev_sync_tournaments(c, dry_run=dry_run)


# Dev environment tasks (uses docker-compose.debug.yaml)
@task
def dev_up(c: Context, sync: bool = True) -> None:
    """Start dev environment, optionally sync data from production.

    Args:
        sync: If True (default), sync users, tournaments, and Steam stats from production.
              Use --no-sync to skip syncing and just start containers.
    """
    if sync:
        docker_compose_up(c, "dev", detach=True)

        _wait_for_backend(c, "dev")

        print("\n=== Syncing data from production ===")
        dev_sync_all(c)

        print("\n=== Pulling Steam matchmaking stats ===")
        db_populate_steam(c, paths.DEBUG_ENV_FILE, full_sync=False, relink=True)

        print("\n=== Auto-linking tournament games ===")
        _auto_link_all_tournaments(c, "dev")

        print("\n=== Sync complete, attaching to logs ===")
        docker_compose_logs(c, "dev")
    else:
        docker_compose_up(c, "dev")


@task
def dev_down(c: Context) -> None:
    docker_compose_down(c, "dev")


@task
def dev_logs(c: Context) -> None:
    docker_compose_logs(c, "dev")


@task
def dev_ps(c: Context) -> None:
    docker_compose_ps(c, "dev")


@task
def dev_restart(c: Context) -> None:
    docker_compose_restart(c, "dev")


@task
def dev_stop(c: Context) -> None:
    docker_compose_stop(c, "dev")


@task
def dev_build(c: Context) -> None:
    docker_compose_build(c, "dev")


@task
def dev_pull(c: Context) -> None:
    docker_compose_pull(c, "dev")


@task
def dev_top(c: Context) -> None:
    docker_compose_top(c, "dev")


@task
def dev_exec(c: Context, service: str, cmd: str) -> None:
    docker_compose_exec(c, "dev", service, cmd)


@task
def dev_run(c: Context, service: str = "backend", cmd: str = "") -> None:
    """Run a one-off command in dev environment. Example: inv dev.run --cmd 'python manage.py test'"""
    docker_compose_run(c, "dev", service, cmd)


@task
def dev_upd(c: Context) -> None:
    """Start dev environment in detached mode."""
    docker_compose_up(c, "dev", detach=True)


ns_dev.add_task(dev_up, "up")
ns_dev.add_task(dev_upd, "upd")
ns_dev.add_task(dev_down, "down")
ns_dev.add_task(dev_logs, "logs")
ns_dev.add_task(dev_ps, "ps")
ns_dev.add_task(dev_restart, "restart")
ns_dev.add_task(dev_stop, "stop")
ns_dev.add_task(dev_build, "build")
ns_dev.add_task(dev_pull, "pull")
ns_dev.add_task(dev_top, "top")
ns_dev.add_task(dev_exec, "exec")
ns_dev.add_task(dev_run, "run")
ns_dev.add_task(dev_sync_users, "sync-users")
ns_dev.add_task(dev_sync_tournaments, "sync-tournaments")
ns_dev.add_task(dev_sync_all, "sync-all")


# Test environment tasks (uses docker-compose.test.yaml)
# Note: ns_test is imported from scripts.tests which already has cypress tasks


@task(name="test-up")
def test_up(c: Context) -> None:
    docker_compose_up(c, "test")


@task(name="test-down")
def test_down(c: Context) -> None:
    docker_compose_down(c, "test")


@task(name="test-logs")
def test_logs(c: Context) -> None:
    docker_compose_logs(c, "test")


@task(name="test-ps")
def test_ps(c: Context) -> None:
    docker_compose_ps(c, "test")


@task(name="test-restart")
def test_restart(c: Context) -> None:
    docker_compose_restart(c, "test")


@task(name="test-stop")
def test_stop(c: Context) -> None:
    docker_compose_stop(c, "test")


@task(name="test-build")
def test_build(c: Context) -> None:
    docker_compose_build(c, "test")


@task(name="test-pull")
def test_pull(c: Context) -> None:
    docker_compose_pull(c, "test")


@task(name="test-top")
def test_top(c: Context) -> None:
    docker_compose_top(c, "test")


@task(name="test-exec")
def test_exec(c: Context, service: str, cmd: str) -> None:
    docker_compose_exec(c, "test", service, cmd)


@task(name="test-run")
def test_run(c: Context, service: str = "backend", cmd: str = "") -> None:
    """Run a one-off command in test environment. Example: inv test.run --cmd 'python manage.py test app.tests -v 2'"""
    docker_compose_run(c, "test", service, cmd, entrypoint="")


@task(name="test-upd")
def test_upd(c: Context) -> None:
    """Start test environment in detached mode."""
    docker_compose_up(c, "test", detach=True)


ns_test.add_task(test_up, "up")
ns_test.add_task(test_upd, "upd")
ns_test.add_task(test_down, "down")
ns_test.add_task(test_logs, "logs")
ns_test.add_task(test_ps, "ps")
ns_test.add_task(test_restart, "restart")
ns_test.add_task(test_stop, "stop")
ns_test.add_task(test_build, "build")
ns_test.add_task(test_pull, "pull")
ns_test.add_task(test_top, "top")
ns_test.add_task(test_exec, "exec")
ns_test.add_task(test_run, "run")


# Prod environment tasks (uses docker-compose.prod.yaml)
@task
def prod_up(c: Context) -> None:
    docker_compose_up(c, "prod")


@task
def prod_down(c: Context) -> None:
    docker_compose_down(c, "prod")


@task
def prod_logs(c: Context) -> None:
    docker_compose_logs(c, "prod")


@task
def prod_ps(c: Context) -> None:
    docker_compose_ps(c, "prod")


@task
def prod_restart(c: Context) -> None:
    docker_compose_restart(c, "prod")


@task
def prod_stop(c: Context) -> None:
    docker_compose_stop(c, "prod")


@task
def prod_build(c: Context) -> None:
    docker_compose_build(c, "prod")


@task
def prod_pull(c: Context) -> None:
    docker_compose_pull(c, "prod")


@task
def prod_top(c: Context) -> None:
    docker_compose_top(c, "prod")


@task
def prod_exec(c: Context, service: str, cmd: str) -> None:
    docker_compose_exec(c, "prod", service, cmd)


@task
def prod_run(c: Context, service: str = "backend", cmd: str = "") -> None:
    """Run a one-off command in prod environment. Example: inv prod.run --cmd 'python manage.py shell'"""
    docker_compose_run(c, "prod", service, cmd)


@task
def prod_upd(c: Context) -> None:
    """Start prod environment in detached mode."""
    docker_compose_up(c, "prod", detach=True)


ns_prod.add_task(prod_up, "up")
ns_prod.add_task(prod_upd, "upd")
ns_prod.add_task(prod_down, "down")
ns_prod.add_task(prod_logs, "logs")
ns_prod.add_task(prod_ps, "ps")
ns_prod.add_task(prod_restart, "restart")
ns_prod.add_task(prod_stop, "stop")
ns_prod.add_task(prod_build, "build")
ns_prod.add_task(prod_pull, "pull")
ns_prod.add_task(prod_top, "top")
ns_prod.add_task(prod_exec, "exec")
ns_prod.add_task(prod_run, "run")


# =============================================================================
# Discord Bot Tasks
# =============================================================================

ns_discord = Collection("discord")


@task
def discord_ngrok(c: Context, port: int = 443) -> None:
    """Start ngrok tunnel for Discord bot interactions.

    This exposes the local server to the internet so Discord can send
    interaction webhooks. After starting, copy the HTTPS URL and set it
    as your Interactions Endpoint URL in the Discord Developer Portal.

    The endpoint URL will be: <ngrok-url>/discord/interactions/

    Args:
        port: Local port to tunnel (default: 443 for HTTPS via nginx)
    """
    print("Starting ngrok tunnel for Discord interactions...")
    print("")
    print("After ngrok starts:")
    print("1. Copy the HTTPS 'Forwarding' URL (e.g., https://abc123.ngrok.io)")
    print("2. Go to Discord Developer Portal > Your App > General Information")
    print("3. Set 'Interactions Endpoint URL' to: <ngrok-url>/discord/interactions/")
    print("4. Discord will send a PING to verify - check backend logs for confirmation")
    print("")
    # Use --host-header to preserve the host and skip cert verification for self-signed certs
    c.run(f"ngrok http https://localhost:{port} --host-header=localhost", pty=True)


@task
def discord_logs(c: Context, stack: str = "dev") -> None:
    """Show logs from the Discord bot container (default: the dev stack ngrok serves)."""
    if stack not in STACKS:
        raise _fail(
            SlotError(f"--stack must be one of {', '.join(STACKS)}, not {stack}")
        )
    run_compose(
        c, cast(Stack, stack), "logs", "-f", "--tail=100", "discord-bot", pty=True
    )


ns_discord.add_task(discord_ngrok, "ngrok")
ns_discord.add_task(discord_logs, "logs")
ns.add_collection(ns_discord, "discord")
