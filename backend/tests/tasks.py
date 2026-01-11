import os
from pathlib import Path

from invoke import Collection, task

from paths import BACKEND_PATH, PROJECT_PATH, TEST_DB_PATH, TEST_ENV_FILE

ns_dbtest = Collection("test")
from dotenv import load_dotenv

from backend.tasks import db_migrate_test


def load_env(c):
    load_dotenv(TEST_ENV_FILE)


@task
def run_tests(c):
    load_env(c)
    # Create a fresh test.db.sqlite3
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    TEST_DB_PATH.touch()

    with c.cd(BACKEND_PATH.absolute()):
        cmd = "DISABLE_CACHE=true pytest -vvv  -s -c pytest.ini"
        c.run(cmd, pty=True)


ns_dbtest.add_task(run_tests, "all")
