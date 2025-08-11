from pathlib import Path

try:
    import toml
except ImportError:
    toml = None
from alive_progress import alive_bar
from invoke.collection import Collection
from invoke.tasks import task
from backend.tasks import db_migrate
from scripts.docker import docker_pull_all


import paths

from .utils import get_version, crun

ns_update = Collection("update")


@task
def git(c):
    crun(c, "git pull")


@task
def python(c):
    crun(c, "poetry install")


@task
def npm(c):
    with c.cd(paths.FRONTEND_PATH):

        c.run("npm install")


@task
def all(c):
    git(c)
    python(c)
    npm(c)
    db_migrate(c)
    docker_pull_all(c)


ns_update.add_task(git, name="git")
ns_update.add_task(python, name="python")
ns_update.add_task(npm, name="npm")
ns_update.add_task(all, name="all")
