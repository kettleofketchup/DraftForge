from pathlib import Path

import semver
from invoke import UnexpectedExit
from invoke.collection import Collection
from invoke.tasks import task

import paths
from backend.tasks import ns_db
from scripts.docker import docker_pull_all, ns_docker
from scripts.docs import ns_docs
from scripts.sync_version import (
    get_version_from_env,
    get_version_from_pyproject,
    update_env_version,
    update_pyproject_version,
)
from scripts.tests import dev_test, ns_demo, ns_test
from scripts.update import ns_update
from scripts.utils import crun, get_version
from scripts.version import ns_version

config = None
version = None

import invoke
from rich.traceback import install

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
from dotenv import load_dotenv


def docker_stop_all(c):
    """Stop and remove all Docker containers."""
    result = c.run("docker ps -aq", hide=True, warn=True)
    if result.stdout.strip():
        c.run("docker stop $(docker ps -aq)", warn=True)
        c.run("docker rm $(docker ps -aq)", warn=True)


def docker_compose_down(c, compose_file: Path):
    docker_stop_all(c)
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} down --remove-orphans"
        )
        c.run(cmd)


def docker_compose_up(c, compose_file: Path, detach: bool = False):
    with c.cd(paths.PROJECT_PATH):
        detach_flag = "-d" if detach else ""
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} up {detach_flag} --remove-orphans"
        )
        c.run(cmd)


def docker_compose_logs(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} logs -f"
        )
        c.run(cmd)


def docker_compose_ps(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} ps"
        )
        c.run(cmd)


def docker_compose_restart(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} restart"
        )
        c.run(cmd)


def docker_compose_stop(c, compose_file: Path):
    docker_stop_all(c)
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} stop"
        )
        c.run(cmd)


def docker_compose_build(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} build"
        )
        c.run(cmd)


def docker_compose_pull(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} pull"
        )
        c.run(cmd)


def docker_compose_top(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} top"
        )
        c.run(cmd)


def docker_compose_exec(c, compose_file: Path, service: str, cmd_str: str):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} exec {service} {cmd_str}"
        )
        c.run(cmd, pty=True)


def docker_compose_run(c, compose_file: Path, service: str, cmd_str: str):
    """Run a one-off command in a new container with --rm flag."""
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} run --rm {service} {cmd_str}"
        )
        c.run(cmd, pty=True)


def _wait_for_backend(c, compose_file: Path, timeout: int = 120):
    """Wait for backend container to be healthy and accepting requests."""
    import time

    print("Waiting for backend to be ready...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Check if backend container is running
            result = c.run(
                f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
                f"-f {compose_file.resolve()} ps backend --format json",
                hide=True,
                warn=True,
            )
            if result.ok and "running" in result.stdout.lower():
                # Try to hit the health endpoint
                health_result = c.run(
                    f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
                    f"-f {compose_file.resolve()} exec -T backend "
                    f"python -c \"import requests; requests.get('http://localhost:8000/api/', timeout=5)\"",
                    hide=True,
                    warn=True,
                )
                if health_result.ok:
                    print("Backend is ready!")
                    return True
        except Exception:
            pass
        time.sleep(2)

    print("Warning: Backend health check timed out, proceeding anyway...")
    return False


def _auto_link_all_tournaments(c, compose_file: Path):
    """Run auto-link for all tournaments to link games to Steam matches."""
    print("Auto-linking tournament games to Steam matches...")
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} exec -T backend "
            f'python -c "'
            f"import django; django.setup(); "
            f"from app.models import Tournament; "
            f"from steam.functions.game_linking import auto_link_matches_for_tournament; "
            f"results = [auto_link_matches_for_tournament(t.id) for t in Tournament.objects.all()]; "
            f"linked = sum(r['auto_linked_count'] for r in results); "
            f"suggestions = sum(r['suggestions_created_count'] for r in results); "
            f"print(f'Auto-linked {{linked}} games, created {{suggestions}} suggestions')\""
        )
        c.run(cmd, warn=True)


from backend.tasks import db_migrate, db_populate_steam


@task
def dev_debug(c):

    db_migrate(c, paths.DEBUG_ENV_FILE)
    with c.cd(paths.PROJECT_PATH):
        load_dotenv(paths.DEBUG_ENV_FILE)

        cmd = (
            f"docker compose "
            f"--project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {paths.DOCKER_COMPOSE_DEBUG_PATH.resolve()} "
            f"--ansi always up --no-attach nginx --remove-orphans"
        )
        c.run(cmd)


@task
def dev_live(c):
    cmd = f"./scripts/tmux.sh"
    c.run(cmd, pty=True)


@task
def dev_prod(c):
    with c.cd(paths.PROJECT_PATH):

        load_dotenv(paths.PROD_ENV_FILE)
        db_migrate(c, paths.PROD_ENV_FILE)
    cmd = f"docker compose -p . -f {paths.DOCKER_COMPOSE_PROD_PATH.resolve()} up"
    c.run(cmd)


@task
def dev_mac(c):
    with c.cd(paths.PROJECT_PATH):

        load_dotenv(paths.DEBUG_ENV_FILE)

        load_dotenv(paths.PROD_ENV_FILE)
        db_migrate(c, paths.PROD_ENV_FILE)

        cmd = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_DEBUG_M1_PATH.resolve()} up"
        c.run(cmd)


@task
def dev_release(c):
    import os
    import sys

    # Read VERSION from .env.release and set it as environment variable
    with c.cd(paths.PROJECT_PATH):

        load_dotenv(paths.RELEASE_ENV_FILE)
        db_migrate(c, paths.RELEASE_ENV_FILE)
        docker_pull_all(c)

        version = get_version_from_env(paths.RELEASE_ENV_FILE.resolve())
        print(f"launching release version {version}")
        cmd1 = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_RELEASE_PATH.resolve()} down "
        cmd2 = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_RELEASE_PATH.resolve()} up -d"

        c.run(cmd1)
        c.run(cmd2)


@task
def dev_release(c):
    import os
    import sys

    # Read VERSION from .env.release and set it as environment variable
    with c.cd(paths.PROJECT_PATH):

        load_dotenv(paths.RELEASE_ENV_FILE)
        db_migrate(c, paths.RELEASE_ENV_FILE)
        docker_pull_all(c)

        version = get_version_from_env(paths.RELEASE_ENV_FILE.resolve())
        print(f"launching release version {version}")
        cmd1 = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_RELEASE_PATH.resolve()} down "
        cmd2 = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_RELEASE_PATH.resolve()} up -d"

        c.run(cmd1)
        c.run(cmd2)


@task
def certbot(c):
    cmd = "certbot certonly --register-unsafely-without-email"
    cmd += " --agree-tos --force-renewal"

    cmd += f" --webroot --webroot-path {str(paths.CERTBOT_WEBROOT.absolute())}"
    cmd += f" --work-dir {str(paths.CERTBOT_WORK.absolute())}"

    cmd += f" --config-dir {str(paths.CERTBOT_CONFIGS.absolute())}"
    cmd += f" --logs-dir {str(paths.CERTBOT_LOGS.absolute())}"

    for domain in paths.domains:
        cmd += f" -d {domain}"
    print(cmd)
    print()
    c.run(cmd)


ns_prod.add_task(certbot, "certbot")

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
def dev_sync_users(c, dry_run=False):
    """Sync users from production (dota.kettle.sh) to local dev database."""
    load_dotenv(paths.DEBUG_ENV_FILE)
    db_migrate(c, paths.DEBUG_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        flags = "--dry-run" if dry_run else ""
        cmd = f"DISABLE_CACHE=true python manage.py sync_prod_users {flags}"
        c.run(cmd, pty=True)


@task
def dev_sync_tournaments(c, dry_run=False):
    """Sync tournaments from production (dota.kettle.sh) to local dev database."""
    load_dotenv(paths.DEBUG_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        flags = "--dry-run" if dry_run else ""
        cmd = f"DISABLE_CACHE=true python manage.py sync_prod_tournaments {flags}"
        c.run(cmd, pty=True)


@task
def dev_sync_all(c, dry_run=False):
    """Sync all data (users, tournaments) from production to local dev database."""
    dev_sync_users(c, dry_run=dry_run)
    dev_sync_tournaments(c, dry_run=dry_run)


# Dev environment tasks (uses docker-compose.debug.yaml)
@task
def dev_up(c, sync: bool = True):
    """Start dev environment, optionally sync data from production.

    Args:
        sync: If True (default), sync users, tournaments, and Steam stats from production.
              Use --no-sync to skip syncing and just start containers.
    """
    if sync:
        # Start containers in detached mode first
        docker_compose_up(c, paths.DOCKER_COMPOSE_DEBUG_PATH, detach=True)

        # Wait for backend to be ready
        _wait_for_backend(c, paths.DOCKER_COMPOSE_DEBUG_PATH)

        # Sync users and tournaments from production
        print("\n=== Syncing data from production ===")
        dev_sync_all(c)

        # Pull Steam matchmaking stats
        print("\n=== Pulling Steam matchmaking stats ===")
        db_populate_steam(c, paths.DEBUG_ENV_FILE, full_sync=False, relink=True)

        # Auto-link tournament games to Steam matches
        print("\n=== Auto-linking tournament games ===")
        _auto_link_all_tournaments(c, paths.DOCKER_COMPOSE_DEBUG_PATH)

        # Attach to logs
        print("\n=== Sync complete, attaching to logs ===")
        docker_compose_logs(c, paths.DOCKER_COMPOSE_DEBUG_PATH)
    else:
        # Just start containers normally
        docker_compose_up(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_down(c):
    docker_compose_down(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_logs(c):
    docker_compose_logs(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_ps(c):
    docker_compose_ps(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_restart(c):
    docker_compose_restart(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_stop(c):
    docker_compose_stop(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_build(c):
    docker_compose_build(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_pull(c):
    docker_compose_pull(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_top(c):
    docker_compose_top(c, paths.DOCKER_COMPOSE_DEBUG_PATH)


@task
def dev_exec(c, service, cmd):
    docker_compose_exec(c, paths.DOCKER_COMPOSE_DEBUG_PATH, service, cmd)


@task
def dev_run(c, service="backend", cmd=""):
    """Run a one-off command in dev environment. Example: inv dev.run --cmd 'python manage.py test'"""
    docker_compose_run(c, paths.DOCKER_COMPOSE_DEBUG_PATH, service, cmd)


@task
def dev_upd(c):
    """Start dev environment in detached mode."""
    docker_compose_up(c, paths.DOCKER_COMPOSE_DEBUG_PATH, detach=True)


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
def test_up(c):
    docker_compose_up(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-down")
def test_down(c):
    docker_compose_down(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-logs")
def test_logs(c):
    docker_compose_logs(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-ps")
def test_ps(c):
    docker_compose_ps(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-restart")
def test_restart(c):
    docker_compose_restart(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-stop")
def test_stop(c):
    docker_compose_stop(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-build")
def test_build(c):
    docker_compose_build(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-pull")
def test_pull(c):
    docker_compose_pull(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-top")
def test_top(c):
    docker_compose_top(c, paths.DOCKER_COMPOSE_TEST_PATH)


@task(name="test-exec")
def test_exec(c, service, cmd):
    docker_compose_exec(c, paths.DOCKER_COMPOSE_TEST_PATH, service, cmd)


@task(name="test-run")
def test_run(c, service="backend", cmd=""):
    """Run a one-off command in test environment. Example: inv test.run --cmd 'python manage.py test app.tests -v 2'"""
    docker_compose_run(c, paths.DOCKER_COMPOSE_TEST_PATH, service, cmd)


@task(name="test-upd")
def test_upd(c):
    """Start test environment in detached mode."""
    docker_compose_up(c, paths.DOCKER_COMPOSE_TEST_PATH, detach=True)


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
def prod_up(c):
    docker_compose_up(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_down(c):
    docker_compose_down(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_logs(c):
    docker_compose_logs(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_ps(c):
    docker_compose_ps(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_restart(c):
    docker_compose_restart(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_stop(c):
    docker_compose_stop(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_build(c):
    docker_compose_build(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_pull(c):
    docker_compose_pull(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_top(c):
    docker_compose_top(c, paths.DOCKER_COMPOSE_PROD_PATH)


@task
def prod_exec(c, service, cmd):
    docker_compose_exec(c, paths.DOCKER_COMPOSE_PROD_PATH, service, cmd)


@task
def prod_run(c, service="backend", cmd=""):
    """Run a one-off command in prod environment. Example: inv prod.run --cmd 'python manage.py shell'"""
    docker_compose_run(c, paths.DOCKER_COMPOSE_PROD_PATH, service, cmd)


@task
def prod_upd(c):
    """Start prod environment in detached mode."""
    docker_compose_up(c, paths.DOCKER_COMPOSE_PROD_PATH, detach=True)


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
def discord_ngrok(c, port=443):
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
def discord_logs(c):
    """Show logs from the Discord bot container."""
    c.run(
        "docker logs -f captain-user-popover-discord-bot-1 2>&1 | tail -100", pty=True
    )


ns_discord.add_task(discord_ngrok, "ngrok")
ns_discord.add_task(discord_logs, "logs")
ns.add_collection(ns_discord, "discord")
