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


# =============================================================================
# Demo Video Recording Collection
# =============================================================================

ns_demo = Collection("demo")


@task
def demo_create(c, spec=""):
    """Record demo videos for documentation.

    Runs Playwright demo tests with video recording enabled.
    Videos are saved to docs/assets/videos/ and can be committed to git.

    Usage:
        inv demo.create                  # Record all demos
        inv demo.create --spec shuffle   # Record only shuffle draft demo
        inv demo.create --spec snake     # Record only snake draft demo
        inv demo.create --spec herodraft # Record only herodraft demo

    Args:
        spec: Optional pattern to filter which demo to record
    """
    import shutil
    from pathlib import Path

    flush_test_redis(c)

    # Create output directories
    demo_results = paths.FRONTEND_PATH / "demo-results"
    videos_dir = demo_results / "videos"
    docs_videos = paths.PROJECT_PATH / "docs" / "assets" / "videos"

    docs_videos.mkdir(parents=True, exist_ok=True)

    # Run demo tests with video recording
    with c.cd(paths.FRONTEND_PATH):
        grep_arg = f'--grep "{spec}"' if spec else ""
        c.run(
            f"npx playwright test --config=playwright.demo.config.ts {grep_arg}".strip(),
            warn=True,
        )

    # Copy videos to docs/assets/videos/
    if videos_dir.exists():
        print("\nCopying demo videos to docs/assets/videos/...")
        for video_file in videos_dir.glob("*.webm"):
            dest = docs_videos / video_file.name
            shutil.copy2(video_file, dest)
            print(f"  Copied: {video_file.name}")

        # Also copy from test-results if any exist there
        test_results = paths.FRONTEND_PATH / "demo-results"
        for test_dir in test_results.glob("*"):
            if test_dir.is_dir():
                for video_file in test_dir.glob("*.webm"):
                    # Create descriptive name from test
                    dest_name = f"{test_dir.name}.webm"
                    dest = docs_videos / dest_name
                    shutil.copy2(video_file, dest)
                    print(f"  Copied: {dest_name}")

    print(f"\nDemo videos saved to: {docs_videos}")
    print("Commit these videos to git for documentation.")


@task
def demo_shuffle(c):
    """Record shuffle draft demo video."""
    demo_create(c, spec="shuffle")


@task
def demo_snake(c):
    """Record snake draft demo video."""
    demo_create(c, spec="snake")


@task
def demo_herodraft(c):
    """Record herodraft with bracket demo video."""
    demo_create(c, spec="herodraft")


@task
def demo_clean(c):
    """Clean demo output directories."""
    import shutil

    demo_results = paths.FRONTEND_PATH / "demo-results"
    if demo_results.exists():
        shutil.rmtree(demo_results)
        print(f"Cleaned: {demo_results}")


@task
def demo_gifs(c, duration=10, fps=12, width=400):
    """Convert demo videos to GIFs (first N seconds only).

    Creates lightweight GIF previews from demo videos for documentation.
    Uses FFmpeg with palette optimization for high-quality output.

    Usage:
        inv demo.gifs                    # Convert all videos to GIFs
        inv demo.gifs --duration 5       # Only first 5 seconds
        inv demo.gifs --fps 15           # Higher framerate (larger files)
        inv demo.gifs --width 300        # Smaller width (smaller files)

    Args:
        duration: Number of seconds to capture (default: 10)
        fps: Frames per second (default: 12, lower = smaller file)
        width: Output width in pixels (default: 400, height auto-scaled)

    Requires: FFmpeg (install via: sudo apt install ffmpeg)
    """
    import shutil

    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        print("ERROR: FFmpeg is not installed.")
        print("")
        print("Install FFmpeg:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  macOS:         brew install ffmpeg")
        print("  Windows:       choco install ffmpeg")
        return

    docs_videos = paths.PROJECT_PATH / "docs" / "assets" / "videos"
    docs_gifs = paths.PROJECT_PATH / "docs" / "assets" / "gifs"
    docs_gifs.mkdir(parents=True, exist_ok=True)

    # Find all webm videos
    videos = list(docs_videos.glob("*.webm"))
    if not videos:
        print("No demo videos found in docs/assets/videos/")
        print("Run 'inv demo.create' first to record demo videos.")
        return

    print(f"Converting {len(videos)} videos to GIFs...")
    print(f"  Duration: {duration}s, FPS: {fps}, Width: {width}px\n")

    for video in videos:
        gif_name = video.stem + ".gif"
        gif_path = docs_gifs / gif_name

        print(f"Converting: {video.name} -> {gif_name}")

        # FFmpeg two-pass GIF with palette optimization
        # This produces much better quality than single-pass
        ffmpeg_cmd = (
            f'ffmpeg -y -t {duration} -i "{video}" '
            f'-vf "fps={fps},scale={width}:-1:flags=lanczos,'
            f"split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
            f'[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" '
            f'-loop 0 "{gif_path}"'
        )

        result = c.run(ffmpeg_cmd, warn=True, hide=True)
        if result.ok:
            # Get file size
            size_kb = gif_path.stat().st_size / 1024
            print(f"  Created: {gif_name} ({size_kb:.1f} KB)")
        else:
            print(f"  FAILED: {gif_name}")
            print(
                f"  Error: {result.stderr[:200] if result.stderr else 'Unknown error'}"
            )

    print(f"\nGIFs saved to: {docs_gifs}")


@task
def demo_quick(c, duration=10, fps=12, width=400):
    """Record demos and create GIF previews in one step.

    Combines demo.create and demo.gifs for convenience.
    Creates both full videos and 10-second GIF previews.

    Usage:
        inv demo.quick                   # Record all demos + create GIFs
        inv demo.quick --duration 5      # 5-second GIF previews

    Args:
        duration: GIF duration in seconds (default: 10)
        fps: GIF frames per second (default: 12)
        width: GIF width in pixels (default: 400)
    """
    demo_create(c)
    demo_gifs(c, duration=duration, fps=fps, width=width)


ns_demo.add_task(demo_create, "create")
ns_demo.add_task(demo_shuffle, "shuffle")
ns_demo.add_task(demo_snake, "snake")
ns_demo.add_task(demo_herodraft, "herodraft")
ns_demo.add_task(demo_gifs, "gifs")
ns_demo.add_task(demo_quick, "quick")
ns_demo.add_task(demo_clean, "clean")

ns_test.add_collection(ns_demo, "demo")
