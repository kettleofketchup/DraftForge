from invoke.collection import Collection
from invoke.tasks import task
import toml
from pathlib import Path
import paths
from scripts.docker import ns_docker

config = None
version = None


ns = Collection()
ns_dev = Collection("dev")

ns.add_collection(ns_docker, "docker")
ns.add_collection(ns_dev, "dev")


@task
def dev_debug(c):
    cmd = f"docker-compose -f docker-compose.debug.yaml --ansi always up --no-attach nginx --remove-orphans"
    c.run(cmd)


@task
def dev_live(c):
    cmd = f"./scripts/tmux.sh"
    c.run(cmd, pty=True)


@task
def dev_prod(c):
    cmd = f"docker-compose -f docker-compose.yaml up"
    c.run(cmd)


ns_dev.add_task(dev_live, "live")
ns_dev.add_task(dev_debug, "debug")
ns_dev.add_task(dev_prod, "prod")
