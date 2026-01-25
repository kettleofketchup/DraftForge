from dotenv import load_dotenv
from invoke import Collection, task

from backend.tasks import db_migrate
from backend.tests.tasks import ns_dbtest
from backend.tests.tasks import run_tests as run_db_tests
from scripts.docker import docker_build_all

ns_test = Collection("test")
ns_runner = Collection("runner")
ns_cicd = Collection("cicd")
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


ns_test.add_task(setup, "setup")


# =============================================================================
# Playwright Test Collections
# =============================================================================

ns_playwright = Collection("playwright")


@task
def playwright_install(c):
    """Install Playwright browsers."""
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright install")


@task
def playwright_headless(c, args=""):
    """Run all Playwright tests headless.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test {args}".strip())


@task
def playwright_headed(c, args=""):
    """Run all Playwright tests headed (visible browser).

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test --headed {args}".strip())


@task
def playwright_ui(c):
    """Open Playwright UI mode for interactive test development."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --ui")


@task
def playwright_debug(c):
    """Run Playwright tests in debug mode."""
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright test --debug")


@task
def playwright_spec(c, spec="", args=""):
    """Run Playwright tests for a specific spec pattern.

    Usage:
        inv test.playwright.spec --spec herodraft  # Runs herodraft tests
        inv test.playwright.spec --spec navigation # Runs navigation tests
        inv test.playwright.spec --spec herodraft --args "--shard=1/4"

    Args:
        spec: Grep pattern to filter tests
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        if spec:
            c.run(f'npx playwright test --grep "{spec}" {args}'.strip())
        else:
            c.run(f"npx playwright test {args}".strip())


@task
def playwright_report(c):
    """Show Playwright HTML report."""
    with c.cd(paths.FRONTEND_PATH):
        c.run("npx playwright show-report")


@task
def playwright_navigation(c, args=""):
    """Run Playwright navigation tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"npx playwright test tests/playwright/e2e/00-hydration-handling.spec.ts tests/playwright/e2e/01-navigation.spec.ts {args}".strip()
        )


@task
def playwright_tournament(c, args=""):
    """Run Playwright tournament tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"npx playwright test tests/playwright/e2e/03-tournaments/ tests/playwright/e2e/04-tournament/ {args}".strip()
        )


@task
def playwright_draft(c, args=""):
    """Run Playwright draft tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"npx playwright test tests/playwright/e2e/07-draft/ tests/playwright/e2e/08-shuffle-draft/ {args}".strip()
        )


@task
def playwright_bracket(c, args=""):
    """Run Playwright bracket tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test tests/playwright/e2e/09-bracket/ {args}".strip())


@task
def playwright_league(c, args=""):
    """Run Playwright league tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test tests/playwright/e2e/10-leagues/ {args}".strip())


@task
def playwright_herodraft(c, args=""):
    """Run Playwright herodraft tests (headless).

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test tests/playwright/e2e/herodraft/ {args}".strip())


@task
def playwright_herodraft_headed(c):
    """Run Playwright herodraft tests with visible browsers.

    Opens two browser windows side-by-side to watch captains draft simultaneously.
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            "HERODRAFT_HEADED=true npx playwright test tests/playwright/e2e/herodraft/ --project=herodraft"
        )


@task
def playwright_mobile(c, args=""):
    """Run Playwright mobile tests with mobile-chrome project.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"npx playwright test tests/playwright/e2e/06-mobile/ --project=mobile-chrome {args}".strip()
        )


@task
def playwright_all(c, args=""):
    """Run all Playwright tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"npx playwright test {args}".strip())


# Add tasks to playwright collection
ns_playwright.add_task(playwright_install, "install")
ns_playwright.add_task(playwright_headless, "headless")
ns_playwright.add_task(playwright_headed, "headed")
ns_playwright.add_task(playwright_ui, "ui")
ns_playwright.add_task(playwright_debug, "debug")
ns_playwright.add_task(playwright_spec, "spec")
ns_playwright.add_task(playwright_report, "report")
ns_playwright.add_task(playwright_navigation, "navigation")
ns_playwright.add_task(playwright_tournament, "tournament")
ns_playwright.add_task(playwright_draft, "draft")
ns_playwright.add_task(playwright_bracket, "bracket")
ns_playwright.add_task(playwright_league, "league")
ns_playwright.add_task(playwright_herodraft, "herodraft")
ns_playwright.add_task(playwright_herodraft_headed, "herodraft-headed")
ns_playwright.add_task(playwright_mobile, "mobile")
ns_playwright.add_task(playwright_all, "all")

ns_test.add_collection(ns_playwright, "playwright")


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
def cicd_playwright(c):
    """Run Playwright tests for CI/CD (with setup)."""
    setup(c)
    playwright_all(c)


@task
def cicd_backend(c):
    """Run backend tests for CI/CD."""
    backend_all(c)


@task
def cicd_all(c):
    """Run all tests for CI/CD."""
    cicd_backend(c)
    cicd_playwright(c)


ns_cicd.add_task(cicd_playwright, "playwright")
ns_cicd.add_task(cicd_backend, "backend")
ns_cicd.add_task(cicd_all, "all")

ns_test.add_collection(ns_cicd, "cicd")
