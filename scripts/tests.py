from dotenv import load_dotenv
from invoke import Collection, task

from backend.tasks import db_migrate
from backend.tests.tasks import ns_dbtest
from backend.tests.tasks import run_tests as run_db_tests
from scripts.docker import docker_build_all

ns_test = Collection("tests")
ns_test.add_collection(ns_dbtest, "db")


import paths


def flush_test_redis(c):
    """Flush Redis cache in test environment to ensure fresh data."""
    print("Flushing Redis cache...")
    c.run("docker exec test-redis redis-cli FLUSHALL", warn=True)


@task
def dev_test(c):

    with c.cd(paths.PROJECT_PATH):
        load_dotenv(paths.TEST_ENV_FILE)

        cmd1 = f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} -f {paths.DOCKER_COMPOSE_TEST_PATH.resolve()} down "

        c.run(cmd1)
        cmd = (
            f"docker compose "
            f"--project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {paths.DOCKER_COMPOSE_TEST_PATH.resolve()} "
            f"--ansi always up -d"
        )
        c.run(cmd)


@task
def setup(c):

    from backend.tasks import populate_all
    from scripts.docker import docker_build_all, docker_pull_all
    from scripts.update import update_for_test

    load_dotenv(paths.TEST_ENV_FILE)
    update_for_test(c)
    docker_build_all(c)
    populate_all(c)
    dev_test(c)


@task(pre=[setup])
def cypress_open(c):
    # Flush Redis cache before running tests to ensure fresh bracket data
    flush_test_redis(c)

    with c.cd(paths.FRONTEND_PATH):
        cmd = " npm run test:e2e:open"
        c.run(cmd)


@task(pre=[setup])
def cypress_headless(c):
    # Flush Redis cache before running tests to ensure fresh bracket data
    flush_test_redis(c)

    with c.cd(paths.FRONTEND_PATH):
        cmd = " npm run test:e2e:headless"
        c.run(cmd)


ns_test.add_task(cypress_headless, "headless")


ns_test.add_task(cypress_open, "open")

ns_test.add_task(setup, "setup")
