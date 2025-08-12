from pathlib import Path

try:
    import toml
except ImportError:
    toml = None
from invoke.collection import Collection
from invoke.tasks import task

import paths
from scripts.docker import ns_docker

config = None
version = None


ns_db = Collection("db")
apps = ["steam", "app"]


@task
def db_makemigrations(c):
    with c.cd(paths.BACKEND_PATH.absolute()):
        for app in apps:
            cmd = f"python manage.py makemigrations {app}"
            c.run(cmd, pty=True)

        cmd = f"python manage.py makemigrations"
        c.run(cmd, pty=True)


@task(pre=[db_makemigrations])
def db_migrate(c):
    with c.cd(paths.BACKEND_PATH.absolute()):
        for app in apps:
            cmd = f"python manage.py migrate {app}"
            c.run(cmd, pty=True)

        cmd = f"python manage.py migrate"
        c.run(cmd, pty=True)


# @task(pre=[db_migrate])
# def db_fill(c):
#     """Fill the database with initial data."""
#     with c.cd(paths.BACKEND_PATH.absolute()):
#         # cmd = f"python manage.py shell < tests/faker.py"
#         # c.run(cmd, pty=True)
#         populate_data()
#         # Populate the database with fake data


ns_db.add_task(db_migrate, "migrate")
ns_db.add_task(db_makemigrations, "makemigrations")
# ns_db.add_task(db_fill, "fill")
