from dotenv import load_dotenv
from invoke import Collection, task

from backend.tasks import db_migrate
from backend.tests.tasks import ns_dbtest
from backend.tests.tasks import run_tests as run_db_tests
from scripts.docker import docker_build_all

ns_test = Collection("test")
ns_runner = Collection("runner")
ns_cicd = Collection("cicd")
ns_cypress = Collection("cypress")
ns_backend = Collection("backend")
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


# =============================================================================
# Cypress Test Collections
# =============================================================================


@task
def cypress_draft(c):
    """Run draft-related Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            'npx cypress run --spec "tests/cypress/e2e/07-draft/**/*.cy.ts,tests/cypress/e2e/08-shuffle-draft/**/*.cy.ts"'
        )


@task
def cypress_tournament(c):
    """Run tournament creation Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            'npx cypress run --spec "tests/cypress/e2e/03-tournaments/**/*.cy.ts,tests/cypress/e2e/04-tournament/**/*.cy.ts"'
        )


@task
def cypress_bracket(c):
    """Run bracket-related Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx cypress run --spec "tests/cypress/e2e/09-bracket/**/*.cy.ts"')


@task
def cypress_league(c):
    """Run league-related Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx cypress run --spec "tests/cypress/e2e/10-leagues/**/*.cy.ts"')


@task
def cypress_navigation(c):
    """Run navigation/hydration Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx cypress run --spec "tests/cypress/e2e/0[01]-*.cy.ts"')


@task
def cypress_mobile(c):
    """Run mobile/responsive Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run('npx cypress run --spec "tests/cypress/e2e/06-mobile/**/*.cy.ts"')


@task
def cypress_all(c):
    """Run all Cypress tests."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npm run test:e2e:headless")


# Add tasks to cypress collection
ns_cypress.add_task(cypress_draft, "draft")
ns_cypress.add_task(cypress_tournament, "tournament")
ns_cypress.add_task(cypress_bracket, "bracket")
ns_cypress.add_task(cypress_league, "league")
ns_cypress.add_task(cypress_navigation, "navigation")
ns_cypress.add_task(cypress_mobile, "mobile")
ns_cypress.add_task(cypress_all, "all")

ns_test.add_collection(ns_cypress, "cypress")


# =============================================================================
# Backend Test Collections
# =============================================================================


@task
def backend_all(c):
    """Run all backend tests."""
    run_db_tests(c)


@task
def backend_steam(c):
    """Run Steam-related backend tests."""
    load_dotenv(paths.TEST_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        c.run("DISABLE_CACHE=true pytest -vvv steam/tests/ -c pytest.ini", pty=True)


@task
def backend_draft(c):
    """Run draft-related backend tests."""
    load_dotenv(paths.TEST_ENV_FILE)
    with c.cd(paths.BACKEND_PATH):
        c.run(
            "DISABLE_CACHE=true pytest -vvv app/tests/test_shuffle_draft*.py -c pytest.ini",
            pty=True,
        )


# Add tasks to backend collection
ns_backend.add_task(backend_all, "all")
ns_backend.add_task(backend_steam, "steam")
ns_backend.add_task(backend_draft, "draft")

ns_test.add_collection(ns_backend, "backend")


# =============================================================================
# CI/CD Test Collections
# =============================================================================


@task
def cicd_cypress(c):
    """Run Cypress tests for CI/CD (with setup)."""
    setup(c)
    cypress_all(c)


@task
def cicd_backend(c):
    """Run backend tests for CI/CD."""
    backend_all(c)


@task
def cicd_all(c):
    """Run all tests for CI/CD."""
    cicd_backend(c)
    cicd_cypress(c)


ns_cicd.add_task(cicd_cypress, "cypress")
ns_cicd.add_task(cicd_backend, "backend")
ns_cicd.add_task(cicd_all, "all")

ns_test.add_collection(ns_cicd, "cicd")
