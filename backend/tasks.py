from pathlib import Path

import toml
from invoke.collection import Collection
from invoke.tasks import task

import paths
from scripts.docker import ns_docker

config = None
version = None


ns_db = Collection("db")


@task
def db_makemigrations(c):
    with c.cd(paths.BACKEND_PATH.absolute()):
        cmd = f"python manage.py makemigrations app"
        c.run(cmd, pty=True)
        cmd = f"python manage.py makemigrations"
        c.run(cmd, pty=True)


@task(pre=[db_makemigrations])
def db_migrate(c):
    with c.cd(paths.BACKEND_PATH.absolute()):
        cmd = f"python manage.py migrate app"
        c.run(cmd, pty=True)
        cmd = f"python manage.py migrate"
        c.run(cmd, pty=True)


ns_db.add_task(db_migrate, "migrate")
ns_db.add_task(db_makemigrations, "makemigrations")
