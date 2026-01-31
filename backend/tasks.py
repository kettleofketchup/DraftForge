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
import os

from dotenv import load_dotenv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

ns_db = Collection("db")
ns_db_migrate = Collection("migrate")

ns_db_populate = Collection("populate")
ns_db.add_collection(ns_db_populate, "populate")
ns_db.add_collection(ns_db_migrate, "migrate")
apps = ["steam", "app", "bracket", "discordbot"]


def check_dbs(c):
    for db_path in [paths.TEST_DB_PATH, paths.DEV_DB_PATH, paths.PROD_DB_PATH]:
        if not db_path.exists():
            with c.cd(paths.BACKEND_PATH.absolute()):
                cmd = f"touch {db_path}"
                c.run(cmd, pty=True)


@task
def db_makemigrations(c, path: Path = paths.DEBUG_ENV_FILE):
    load_dotenv(path)
    check_dbs(c)

    with c.cd(paths.BACKEND_PATH.absolute()):
        for app in apps:
            cmd = f"DISABLE_CACHE=true python manage.py makemigrations {app}"
            c.run(cmd, pty=True)

        cmd = f"DISABLE_CACHE=true python manage.py makemigrations"
        c.run(cmd, pty=True)


@task(pre=[])
def db_migrate(c, path: Path = paths.DEBUG_ENV_FILE):
    load_dotenv(path)
    db_makemigrations(c, path)

    """Run migrations for a specific environment."""
    load_dotenv(path, override=True)
    with c.cd(paths.BACKEND_PATH.absolute()):
        for app in apps:
            cmd = f"DISABLE_CACHE=true python manage.py migrate {app}"
            c.run(cmd, pty=True)

        cmd = f"DISABLE_CACHE=true python manage.py migrate"
        c.run(cmd, pty=True)


@task(pre=[])
def db_migrate_test(c):
    db_migrate(c, paths.TEST_ENV_FILE)


@task(pre=[])
def db_migrate_dev(c):
    db_migrate(c, paths.DEBUG_ENV_FILE)


@task(pre=[])
def db_migrate_prod(c):
    db_migrate(c, paths.PROD_ENV_FILE)


@task(pre=[])
def db_migrate_all(c):

    db_migrate_dev(
        c,
    )
    db_migrate_prod(
        c,
    )
    db_migrate_test(
        c,
    )


@task
def db_populate_organizations(c, path: Path = paths.TEST_ENV_FILE, force: bool = False):
    """Populate the database with organizations and leagues."""
    load_dotenv(path)
    db_migrate(c, path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.populate import populate_organizations_and_leagues; populate_organizations_and_leagues(force={force_arg})"'
        c.run(cmd, pty=True)


@task
def db_populate_users(c, path: Path = paths.TEST_ENV_FILE, force: bool = False):
    """Populate the database with Discord users."""

    load_dotenv(path)
    db_migrate(c, path)

    with c.cd(paths.BACKEND_PATH.absolute()):

        force_flag = "--force" if force else ""
        cmd = f"DISABLE_CACHE=true python manage.py populate_users {force_flag}"
        c.run(cmd, pty=True)


# @task(pre=[db_migrate])
# def db_fill(c):
#     """Fill the database with initial data."""
#     with c.cd(paths.BACKEND_PATH.absolute()):
#         # cmd = f"python manage.py shell < tests/faker.py"
#         # c.run(cmd, pty=True)
#         populate_data()
#         # Populate the database with fake data


@task
def db_populate_tournaments(c, path: Path = paths.TEST_ENV_FILE, force: bool = False):
    """Populate the database with 5 tournaments containing random users."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_flag = "--force" if force else ""
        cmd = f"DISABLE_CACHE=true python manage.py populate_tournaments {force_flag}"
        c.run(cmd, pty=True)


@task
def db_populate_steam(
    c, path: Path = paths.TEST_ENV_FILE, full_sync: bool = False, relink: bool = True
):
    """Populate the database with Steam match data from the real Steam API."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        flags = ""
        if full_sync:
            flags += " --full-sync"
        if relink:
            flags += " --relink-users"
        cmd = f"DISABLE_CACHE=true python manage.py populate_steam_matches{flags}"
        c.run(cmd, pty=True)


@task
def db_populate_steam_mock(c, path: Path = paths.TEST_ENV_FILE, force: bool = False):
    """Populate mock Steam matches for testing."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.populate import populate_steam_matches; populate_steam_matches({force_arg})"'
        c.run(cmd, pty=True)


@task
def db_populate_test_tournaments(
    c, path: Path = paths.TEST_ENV_FILE, force: bool = False
):
    """Populate test scenario tournaments for Cypress testing."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.helpers.tournament_config import populate_test_tournaments; populate_test_tournaments(force={force_arg})"'
        c.run(cmd, pty=True)


@task
def db_populate_bracket_linking(
    c, path: Path = paths.TEST_ENV_FILE, force: bool = False
):
    """Populate bracket linking test scenario for Cypress testing."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.populate import populate_bracket_linking_scenario; populate_bracket_linking_scenario(force={force_arg})"'
        c.run(cmd, pty=True)


@task
def db_populate_real_tournament(
    c,
    path: Path = paths.TEST_ENV_FILE,
    force: bool = False,
):
    """Populate database with real tournament 38 data."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.populate import populate_real_tournament_38; populate_real_tournament_38(force={force_arg})"'
        c.run(cmd, pty=True)


@task
def db_populate_demo_tournaments(
    c,
    path: Path = paths.TEST_ENV_FILE,
    force: bool = False,
):
    """Populate database with demo tournaments for video recording."""
    load_dotenv(path)

    with c.cd(paths.BACKEND_PATH.absolute()):
        force_arg = "True" if force else "False"
        cmd = f'DISABLE_CACHE=true python manage.py shell -c "from tests.populate import populate_demo_tournaments; populate_demo_tournaments(force={force_arg})"'
        c.run(cmd, pty=True)


@task
def populate_all(c):
    paths.TEST_DB_PATH.unlink(missing_ok=True)
    paths.TEST_DB_PATH.touch()
    db_migrate_test(c)
    db_populate_organizations(c, paths.TEST_ENV_FILE)
    db_populate_users(c, paths.TEST_ENV_FILE)
    db_populate_tournaments(c, paths.TEST_ENV_FILE)
    db_populate_steam_mock(c, paths.TEST_ENV_FILE)
    db_populate_test_tournaments(c, paths.TEST_ENV_FILE)
    db_populate_bracket_linking(c, paths.TEST_ENV_FILE)
    db_populate_real_tournament(c, paths.TEST_ENV_FILE)
    db_populate_demo_tournaments(c, paths.TEST_ENV_FILE)


ns_db.add_task(db_makemigrations, "makemigrations")
ns_db_populate.add_task(db_populate_organizations, "organizations")
ns_db_populate.add_task(db_populate_users, "users")
ns_db_populate.add_task(db_populate_tournaments, "tournaments")
ns_db_populate.add_task(db_populate_steam, "steam")
ns_db_populate.add_task(db_populate_steam_mock, "steam-mock")
ns_db_populate.add_task(db_populate_test_tournaments, "test-tournaments")
ns_db_populate.add_task(db_populate_bracket_linking, "bracket-linking")
ns_db_populate.add_task(db_populate_real_tournament, "real-tournament")
ns_db_populate.add_task(db_populate_demo_tournaments, "demo-tournaments")
ns_db_populate.add_task(populate_all, "all")

ns_db_migrate.add_task(db_migrate_all, "all")

ns_db_migrate.add_task(db_migrate_dev, "dev", default=True)
ns_db_migrate.add_task(db_migrate_test, "test")
ns_db_migrate.add_task(db_migrate_prod, "prod")

# ns_db.add_task(db_fill, "fill")
