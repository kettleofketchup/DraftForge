from pathlib import Path

import toml
from invoke.collection import Collection
from invoke.tasks import task

import paths
from backend.tasks import ns_db
from scripts.docker import ns_docker

config = None
version = None


ns = Collection()
ns_dev = Collection("dev")
ns_prod = Collection("prod")
ns.add_collection(ns_prod, "prod")

ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")
ns.add_collection(ns_db, "db")


@task
def dev_debug(c):
    cmd = f"docker compose -f docker-compose.debug.yaml --ansi always up --no-attach nginx --remove-orphans"
    c.run(cmd)


@task
def dev_live(c):
    cmd = f"./scripts/tmux.sh"
    c.run(cmd, pty=True)


@task
def dev_prod(c):
    cmd = f"docker compose -f docker-compose.yaml up"
    c.run(cmd)


@task
def dev_mac(c):
    cmd = f"docker compose -f docker-compose.debug.m1.yaml up"
    c.run(cmd)


@task
def dev_release(c):
    cmd1 = f"docker compose -f docker-compose.release.yaml down "
    c.run(cmd1)
    cmd2 = f"docker compose -f docker-compose.release.yaml up -d"
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
