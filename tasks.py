from pathlib import Path

import semver
from invoke import UnexpectedExit
from invoke.collection import Collection
from invoke.tasks import task

import paths
from backend.tasks import ns_db
from scripts.docker import docker_pull_all, ns_docker
from scripts.sync_version import (
    get_version_from_env,
    get_version_from_pyproject,
    update_env_version,
    update_pyproject_version,
)
from scripts.tests import dev_test, ns_test
from scripts.docs import ns_docs
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
ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")
ns.add_collection(ns_db, "db")
ns.add_collection(ns_update, "update")
ns.add_collection(ns_version, "version")
ns.add_collection(ns_test, "test")
ns.add_collection(ns_docs, "docs")
from dotenv import load_dotenv


def docker_compose_down(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} down --remove-orphans"
        )
        c.run(cmd)


def docker_compose_up(c, compose_file: Path):
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {compose_file.resolve()} up --remove-orphans"
        )
        c.run(cmd)


from backend.tasks import db_migrate


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
