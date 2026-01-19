from dotenv import load_dotenv
from invoke import Collection, task

from backend.tasks import db_migrate
from backend.tests.tasks import ns_dbtest
from backend.tests.tasks import run_tests as run_db_tests
from scripts.docker import docker_build_all

ns_test = Collection("test")
ns_runner = Collection("runner")
ns_cicd = Collection("cicd")
ns_test.add_collection(ns_dbtest, "db")
ns_test.add_collection(ns_runner, "runner")


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

    # Ensure test stack is down before setup
    print("Ensuring test stack is down...")
    with c.cd(paths.PROJECT_PATH):
        cmd = (
            f"docker compose --project-directory {paths.PROJECT_PATH.resolve()} "
            f"-f {paths.DOCKER_COMPOSE_TEST_PATH.resolve()} down --remove-orphans"
        )
        c.run(cmd, warn=True)

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


@task
def cypress_headless(c):
    # Flush Redis cache before running tests to ensure fresh bracket data
    flush_test_redis(c)

    with c.cd(paths.FRONTEND_PATH):
        cmd = " npm run test:e2e:headless"
        c.run(cmd)


@task(pre=[setup])
def cicd_headless(c):
    cypress_headless(c)


@task
def cypress_parallel(c, threads=3):
    flush_test_redis(c)

    with c.cd(paths.FRONTEND_PATH):
        cmd = f"npm run test:e2e:parallel"
        c.run(cmd)


@task(pre=[setup])
def cicd_parallel(c, threads=3):
    """Run Cypress tests in parallel using multiple threads.

    Usage:
        inv test.parallel           # Run with 3 threads (default)
        inv test.parallel --threads 4  # Run with 4 threads
    """
    # Flush Redis cache before running tests to ensure fresh bracket data
    cypress_parallel(c, threads)


@task
def cypress_spec(c, spec=""):
    """Run Cypress tests for a specific spec pattern.

    Usage:
        inv test.spec --spec drafts     # Runs 07-draft/*.cy.ts
        inv test.spec --spec tournament # Runs 04-tournament/*.cy.ts
        inv test.spec --spec 01         # Runs 01-*.cy.ts
    """
    # Flush Redis cache before running tests
    flush_test_redis(c)

    with c.cd(paths.FRONTEND_PATH):
        if spec:
            # Map common names to spec patterns
            spec_patterns = {
                "drafts": "tests/cypress/e2e/07-draft/**/*.cy.ts",
                "draft": "tests/cypress/e2e/07-draft/**/*.cy.ts",
                "tournament": "tests/cypress/e2e/04-tournament/**/*.cy.ts",
                "tournaments": "tests/cypress/e2e/03-tournaments/**/*.cy.ts",
                "navigation": "tests/cypress/e2e/01-*.cy.ts",
                "mobile": "tests/cypress/e2e/06-mobile/**/*.cy.ts",
            }
            pattern = spec_patterns.get(spec, f"tests/cypress/e2e/**/*{spec}*.cy.ts")
            cmd = f'npx cypress run --spec "{pattern}"'
        else:
            cmd = "npm run test:e2e:headless"
        c.run(cmd)


ns_test.add_task(cypress_headless, "headless")
ns_test.add_task(cypress_parallel, "parallel")

ns_test.add_task(cypress_spec, "spec")


ns_test.add_task(cypress_open, "open")

ns_test.add_task(setup, "setup")
ns_cicd.add_task(cicd_headless, "headless")

ns_cicd.add_task(cicd_parallel, "run")

ns_test.add_task(cypress_parallel, "parallel")

ns_runner.add_task(cypress_headless, "headless")
ns_runner.add_task(cypress_parallel, "run")

ns_test.add_task(cicd_headless, "headless")
