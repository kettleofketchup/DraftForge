from pathlib import Path

from invoke.collection import Collection
from invoke.tasks import task
from invoke import UnexpectedExit
import paths
from backend.tasks import ns_db
from scripts.docker import ns_docker, docker_pull_all
from scripts.update import ns_update
from scripts.utils import get_version, crun
from scripts.sync_version import (
    get_version_from_pyproject,
    update_env_version,
    get_version_from_env,
    update_pyproject_version,
)

config = None
version = None


ns = Collection()
ns_dev = Collection("dev")
ns_prod = Collection("prod")
ns_version = Collection("version")
ns.add_collection(ns_prod, "prod")

ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")
ns.add_collection(ns_db, "db")
ns.add_collection(ns_update, "update")
ns.add_collection(ns_version, "version")
from dotenv import load_dotenv


@task
def sync_version_from_env(c, env_file=".env.release"):
    """Sync version from environment file to pyproject.toml"""
    # Import functions locally to avoid import issues
    import sys
    import os

    print(f"Syncing version from {env_file}...")
    version = get_version_from_env(env_file)
    print(f"Syncing to version: {version}")
    update_pyproject_version(version)
    print("Version sync complete!")


@task
def sync_version_from_pyproject(c):
    """Sync version from pyproject.toml to environment files"""
    # Import functions locally to avoid import issues
    import sys
    import os

    from scripts.sync_version import get_version_from_pyproject, update_env_version

    print("Syncing version from pyproject.toml...")
    version = get_version_from_pyproject()
    print(f"Syncing to version: {version}")

    # Update environment files
    for env_file in [".env.release", ".env.debug"]:
        update_env_version(env_file, version)

    print("Version sync complete!")


@task
def set_version(c, version):
    """Set version across all files"""
    # Import functions locally to avoid import issues
    import sys
    import os

    from scripts.sync_version import update_pyproject_version, update_env_version

    print(f"Setting version to {version}...")

    # Update pyproject.toml
    update_pyproject_version(version)

    # Update environment files
    for env_file in [".env.release", ".env.prod"]:
        update_env_version(env_file, version)

    print("Version sync complete!")


@task
def build_with_version(c, version=None, env_file=None):
    """Build Docker images with version sync"""
    import os
    import sys

    from scripts.sync_version import (
        get_version_from_env,
        update_pyproject_version,
        update_env_version,
    )

    # Determine the version to use
    if version:
        target_version = version
        print(f"Setting version to {target_version}...")
        # Update all files with the specified version
        update_pyproject_version(target_version)
        for env_file_path in [".env.release", ".env.debug"]:
            update_env_version(env_file_path, target_version)
    elif env_file:
        print(f"Syncing version from {env_file}...")
        target_version = get_version_from_env(env_file)
        print(f"Syncing to version: {target_version}")
        # Update pyproject.toml with version from env file
        update_pyproject_version(target_version)
    else:
        # Default to using .env.release
        env_file = ".env.release"
        print(f"Syncing version from {env_file}...")
        target_version = get_version_from_env(env_file)
        print(f"Syncing to version: {target_version}")
        update_pyproject_version(target_version)

    print(f"Building with VERSION={target_version}")

    # Set environment variable for docker compose
    os.environ["VERSION"] = target_version

    # Build using local compose file
    cmd = f"docker compose -f docker-compose.local.yaml build --build-arg VERSION={target_version}"
    c.run(cmd)

    print(f"Build complete with version {target_version}")


@task
def tag(c):
    version = get_version()
    print(f"Tagging version: {version}")
    crun(c, f"git tag v{version}")

    cmd = f"docker compose -f docker-compose.debug.yaml --ansi always up --no-attach nginx --remove-orphans"
    c.run(cmd)


@task
def dev_debug(c):
    load_dotenv(".env.debug")
    cmd = f"docker compose -f docker-compose.debug.yaml --ansi always up --no-attach nginx --remove-orphans"
    c.run(cmd)


@task
def dev_live(c):
    cmd = f"./scripts/tmux.sh"
    c.run(cmd, pty=True)


@task
def dev_prod(c):
    load_dotenv(".env.prod")
    cmd = f"docker compose -f docker-compose.yaml up"
    c.run(cmd)


@task
def dev_mac(c):

    load_dotenv(".env.debug")

    cmd = f"docker compose -f docker-compose.debug.m1.yaml up"
    c.run(cmd)


@task
def dev_release(c):
    import os
    import sys

    # Read VERSION from .env.release and set it as environment variable

    load_dotenv(".env.release")
    docker_pull_all(c)

    version = get_version_from_env(".env.release")
    print(f"launching release version {version}")
    cmd1 = f"docker compose -f docker-compose.release.yaml down "
    cmd2 = f"docker compose -f docker-compose.release.yaml up -d"

    c.run(cmd1)
    c.run(cmd2)


@task
def dev_migrate(c):
    with c.cd(paths.BACKEND_PATH):
        cmds = [
            f"python manage.py makemigrations app",
            f"python manage.py makemigrations",
            f"python manage.py migrate app",
            f"python manage.py migrate",
        ]
        for cmd in cmds:
            c.run(cmd)


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
ns_dev.add_task(dev_mac, "mac")

ns_dev.add_task(dev_prod, "prod")
ns_dev.add_task(dev_release, "release")
ns_dev.add_task(dev_migrate, "migrate")

ns_version.add_task(sync_version_from_env, "from-env")
ns_version.add_task(sync_version_from_pyproject, "from-pyproject")
ns_version.add_task(set_version, "set")
ns_version.add_task(build_with_version, "build")
