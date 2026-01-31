import os
from pathlib import Path

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


def get_docker_host():
    """Detect DOCKER_HOST based on environment.

    Returns 'nginx' if running inside a Docker container, 'localhost' otherwise.
    Detection checks for /.dockerenv file or 'docker' in /proc/1/cgroup.
    """
    # Check for /.dockerenv (created by Docker)
    if Path("/.dockerenv").exists():
        return "nginx"

    # Check /proc/1/cgroup for 'docker' (Linux containers)
    cgroup_path = Path("/proc/1/cgroup")
    if cgroup_path.exists():
        try:
            content = cgroup_path.read_text()
            if "docker" in content:
                return "nginx"
        except (PermissionError, OSError):
            pass

    return "localhost"


def flush_test_redis(c):
    """Flush Redis cache in test environment to ensure fresh data."""
    print("Flushing Redis cache...")
    result = c.run("docker exec test-redis redis-cli FLUSHALL", warn=True, hide=True)
    if not result.ok:
        c.run("docker exec redis redis-cli FLUSHALL", warn=True, hide=True)


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
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        # Exclude demo project - demos are run separately via inv demo.* commands
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test --project=chromium --project=herodraft {args}".strip()
        )


@task
def playwright_headed(c, args=""):
    """Run all Playwright tests headed (visible browser).

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    # Exclude demo project - demos are run separately via inv demo.* commands
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test --headed --project=chromium --project=herodraft {args}".strip()
        )


@task
def playwright_ui(c):
    """Open Playwright UI mode for interactive test development."""
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"DOCKER_HOST={docker_host} npx playwright test --ui")


@task
def playwright_debug(c):
    """Run Playwright tests in debug mode."""
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"DOCKER_HOST={docker_host} npx playwright test --debug")


@task
def playwright_spec(c, spec="", file="", args=""):
    """Run Playwright tests for a specific spec pattern or file.

    Usage:
        inv test.playwright.spec --spec herodraft  # Runs tests matching "herodraft"
        inv test.playwright.spec --file tests/playwright/e2e/herodraft-captain-connection.spec.ts
        inv test.playwright.spec --spec herodraft --args "--shard=1/4"

    Args:
        spec: Grep pattern to filter tests
        file: Specific test file path to run
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        if file:
            c.run(
                f"DOCKER_HOST={docker_host} npx playwright test {file} {args}".strip()
            )
        elif spec:
            c.run(
                f'DOCKER_HOST={docker_host} npx playwright test --grep "{spec}" {args}'.strip()
            )
        else:
            c.run(f"DOCKER_HOST={docker_host} npx playwright test {args}".strip())


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
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/00-hydration-handling.spec.ts tests/playwright/e2e/01-navigation.spec.ts {args}".strip()
        )


@task
def playwright_tournament(c, args=""):
    """Run Playwright tournament tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/03-tournaments/ tests/playwright/e2e/04-tournament/ {args}".strip()
        )


@task
def playwright_draft(c, args=""):
    """Run Playwright draft tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/07-draft/ tests/playwright/e2e/08-shuffle-draft/ {args}".strip()
        )


@task
def playwright_bracket(c, args=""):
    """Run Playwright bracket tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/09-bracket/ {args}".strip()
        )


@task
def playwright_league(c, args=""):
    """Run Playwright league tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/10-leagues/ {args}".strip()
        )


@task
def playwright_herodraft(c, args=""):
    """Run Playwright herodraft tests (headless).

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} npx playwright test tests/playwright/e2e/herodraft/ {args}".strip()
        )


@task
def playwright_herodraft_headed(c):
    """Run Playwright herodraft tests with visible browsers.

    Opens two browser windows side-by-side to watch captains draft simultaneously.
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(
            f"DOCKER_HOST={docker_host} HERODRAFT_HEADED=true npx playwright test tests/playwright/e2e/herodraft/ --project=herodraft"
        )


@task
def playwright_all(c, args=""):
    """Run all Playwright tests.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    flush_test_redis(c)
    docker_host = get_docker_host()
    with c.cd(paths.FRONTEND_PATH):
        c.run(f"DOCKER_HOST={docker_host} npx playwright test {args}".strip())


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


# Named demo video outputs
DEMO_VIDEO_NAMES = [
    "captain1_herodraft.webm",
    "captain2_herodraft.webm",
    "shuffle_draft.webm",
    "snake_draft.webm",
]

# Demo tournament reset keys
DEMO_RESET_KEYS = {
    "herodraft": "demo_herodraft",
    "shuffle": "demo_shuffle_draft",
    "snake": "demo_snake_draft",
}


def _reset_demo_data(c, demo_key):
    """Reset demo tournament data via API.

    Args:
        c: Invoke context
        demo_key: Demo key (herodraft, shuffle, snake)

    Returns:
        dict: Response data if successful, None otherwise
    """
    import requests

    reset_key = DEMO_RESET_KEYS.get(demo_key)
    if not reset_key:
        print(f"  Warning: No reset key for demo '{demo_key}'")
        return None

    # Use localhost since we're calling from host to Docker container
    url = f"https://localhost/api/tests/demo/{reset_key}/reset/"

    print(f"  Resetting demo data: {reset_key}...")
    try:
        response = requests.post(url, verify=False, timeout=10)
        if response.ok:
            data = response.json()
            print(f"  Reset successful: {data.get('tournament', 'unknown')}")
            return data
        else:
            print(f"  Reset failed: {response.status_code} - {response.text[:100]}")
            return None
    except Exception as e:
        print(f"  Reset failed: {e}")
        return None


def _generate_bracket(c, tournament_pk):
    """Generate bracket for a tournament via test API.

    Args:
        c: Invoke context
        tournament_pk: Tournament primary key

    Returns:
        bool: True if successful
    """
    import requests

    # Use test endpoint (no auth required)
    url = f"https://localhost/api/tests/demo/bracket/{tournament_pk}/generate/"

    print(f"  Generating bracket for tournament {tournament_pk}...")
    try:
        response = requests.post(url, verify=False, timeout=10)
        if response.ok:
            print(f"  Bracket generated successfully")
            return True
        else:
            print(
                f"  Bracket generation failed: {response.status_code} - {response.text[:100]}"
            )
            return False
    except Exception as e:
        print(f"  Bracket generation failed: {e}")
        return False


def _run_demo_in_docker(c, spec="", workers=1):
    """Run Playwright demo tests inside frontend Docker container.

    Args:
        c: Invoke context
        spec: Optional grep pattern to filter demos
        workers: Number of parallel workers (default: 1 for sequential)
    """
    flush_test_redis(c)

    # Build the Playwright command
    grep_arg = f'--grep "{spec}"' if spec else ""
    playwright_cmd = (
        f"npx playwright test --config=playwright.demo.config.ts "
        f"--workers={workers} {grep_arg}"
    ).strip()

    print(f"  Running in Docker: {playwright_cmd}")

    # Execute inside the frontend container (FORCE_COLOR=0 disables ANSI escape codes)
    c.run(
        f'docker exec frontend sh -c "cd /app && FORCE_COLOR=0 {playwright_cmd}"',
        warn=True,
    )


def _copy_demo_videos(c):
    """Copy demo videos from frontend container to docs/assets/videos/."""
    import shutil
    from pathlib import Path

    # Copy from container to host
    demo_results = paths.FRONTEND_PATH / "demo-results"
    videos_dir = demo_results / "videos"
    docs_videos = paths.PROJECT_PATH / "docs" / "assets" / "videos"

    docs_videos.mkdir(parents=True, exist_ok=True)

    # The videos are created by mounted volume, so they should be on host
    if videos_dir.exists():
        print("\nCopying demo videos to docs/assets/videos/...")
        copied_count = 0
        for video_name in DEMO_VIDEO_NAMES:
            video_file = videos_dir / video_name
            if video_file.exists():
                dest = docs_videos / video_name
                shutil.copy2(video_file, dest)
                print(f"  Copied: {video_name}")
                copied_count += 1

        if copied_count == 0:
            print("  No named demo videos found. Check test output for errors.")
        else:
            print(f"\n{copied_count} demo videos saved to: {docs_videos}")
            print("Commit these videos to git for documentation.")
    else:
        print(f"  Warning: Video directory not found: {videos_dir}")


def _copy_demo_snapshots(c):
    """Copy demo snapshots from frontend container to docs/assets/site_snapshots/."""
    import shutil
    from pathlib import Path

    # Copy from container to host
    demo_results = paths.FRONTEND_PATH / "demo-results"
    snapshots_dir = demo_results / "site_snapshots"
    docs_snapshots = paths.PROJECT_PATH / "docs" / "assets" / "site_snapshots"

    docs_snapshots.mkdir(parents=True, exist_ok=True)

    # The snapshots are created by mounted volume, so they should be on host
    if snapshots_dir.exists():
        print("\nCopying snapshots to docs/assets/site_snapshots/...")
        copied_count = 0
        for snapshot_file in snapshots_dir.glob("*.png"):
            dest = docs_snapshots / snapshot_file.name
            shutil.copy2(snapshot_file, dest)
            print(f"  Copied: {snapshot_file.name}")
            copied_count += 1

        if copied_count == 0:
            print("  No snapshots found. Check test output for errors.")
        else:
            print(f"\n{copied_count} snapshots saved to: {docs_snapshots}")
    else:
        print(f"  Warning: Snapshot directory not found: {snapshots_dir}")


@task
def demo_create(c, spec=""):
    """Record demo videos for documentation (runs in Docker).

    Resets demo data, runs Playwright demo tests headless in Docker,
    and copies videos to docs/assets/videos/.

    Named outputs:
    - captain1_herodraft.webm, captain2_herodraft.webm (HeroDraft)
    - shuffle_draft.webm (Shuffle Draft)
    - snake_draft.webm (Snake Draft)

    Usage:
        inv demo.create                  # Record all demos
        inv demo.create --spec shuffle   # Record only shuffle draft demo
        inv demo.create --spec herodraft # Record only herodraft demo

    Args:
        spec: Optional pattern to filter which demo to record
    """
    print("=== Demo Recording ===")

    # Reset all demo data
    if spec:
        _reset_demo_data(c, spec)
    else:
        for demo_key in DEMO_RESET_KEYS:
            _reset_demo_data(c, demo_key)

    # Run demos in Docker
    _run_demo_in_docker(c, spec=spec, workers=1)

    # Copy videos
    _copy_demo_videos(c)


@task
def demo_shuffle(c):
    """Record shuffle draft demo video.

    Resets demo_captaindraft tournament, records shuffle draft demo.
    """
    print("=== Shuffle Draft Demo ===")
    _reset_demo_data(c, "shuffle")
    _run_demo_in_docker(c, spec="shuffle")
    _copy_demo_videos(c)


@task
def demo_snake(c):
    """Record snake draft demo video.

    Resets demo_captaindraft tournament, records snake draft demo.
    """
    print("=== Snake Draft Demo ===")
    _reset_demo_data(c, "snake")
    _run_demo_in_docker(c, spec="snake")
    _copy_demo_videos(c)


@task
def demo_herodraft(c):
    """Record herodraft with bracket demo video.

    Resets demo_herodraft tournament, records hero draft demo.
    """
    print("=== HeroDraft Demo ===")
    _reset_demo_data(c, "herodraft")
    _run_demo_in_docker(c, spec="herodraft")
    _copy_demo_videos(c)


@task
def demo_all(c):
    """Record all demos in parallel.

    Resets all demo data, then runs all demos with 3 workers.
    """
    print("=== Recording All Demos (Parallel) ===")

    # Reset all demo tournaments (deduplicated)
    reset_keys_done = set()
    for demo_key, reset_key in DEMO_RESET_KEYS.items():
        if reset_key not in reset_keys_done:
            _reset_demo_data(c, demo_key)
            reset_keys_done.add(reset_key)

    # Run all demos in parallel
    _run_demo_in_docker(c, workers=3)

    # Copy videos
    _copy_demo_videos(c)


@task
def demo_clean(c):
    """Clean demo output directories."""
    import shutil

    demo_results = paths.FRONTEND_PATH / "demo-results"
    if demo_results.exists():
        shutil.rmtree(demo_results)
        print(f"Cleaned: {demo_results}")


def _get_video_duration(c, video_path):
    """Get video duration in seconds using ffprobe."""
    result = c.run(
        f"ffprobe -v error -show_entries format=duration "
        f'-of default=noprint_wrappers=1:nokey=1 "{video_path}"',
        warn=True,
        hide=True,
    )
    if result.ok and result.stdout.strip():
        return float(result.stdout.strip())
    return None


@task
def demo_gifs(c, duration=10, fps=12, width=400, start_from_middle=True):
    """Convert demo videos to GIFs from the middle of the video.

    Creates lightweight GIF previews from named demo videos for documentation.
    Uses FFmpeg with palette optimization for high-quality output.
    By default, starts from the middle of the video to avoid white screen.

    Named outputs:
    - captain1_herodraft.gif, captain2_herodraft.gif (HeroDraft)
    - shuffle_draft.gif (Shuffle Draft)
    - snake_draft.gif (Snake Draft)

    Usage:
        inv demo.gifs                    # Convert from middle of videos
        inv demo.gifs --duration 5       # Only 5 seconds of content
        inv demo.gifs --fps 15           # Higher framerate (larger files)
        inv demo.gifs --width 300        # Smaller width (smaller files)
        inv demo.gifs --no-start-from-middle  # Start from beginning

    Args:
        duration: Number of seconds to capture (default: 10)
        fps: Frames per second (default: 12, lower = smaller file)
        width: Output width in pixels (default: 400, height auto-scaled)
        start_from_middle: Start from middle of video (default: True)

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

    # Only process named demo videos
    videos = []
    for video_name in DEMO_VIDEO_NAMES:
        video_path = docs_videos / video_name
        if video_path.exists():
            videos.append(video_path)

    if not videos:
        print("No named demo videos found in docs/assets/videos/")
        print("Expected files: " + ", ".join(DEMO_VIDEO_NAMES))
        print("Run 'inv demo.create' first to record demo videos.")
        return

    print(f"Converting {len(videos)} videos to GIFs...")
    print(f"  Duration: {duration}s, FPS: {fps}, Width: {width}px")
    print(f"  Start from middle: {start_from_middle}\n")

    for video in videos:
        gif_name = video.stem + ".gif"
        gif_path = docs_gifs / gif_name

        # Calculate start position
        start_seconds = 0
        if start_from_middle:
            video_duration = _get_video_duration(c, video)
            if video_duration:
                # Start from middle, but ensure we have enough content
                start_seconds = max(0, (video_duration - duration) / 2)
                print(
                    f"Converting: {video.name} -> {gif_name} (from {start_seconds:.1f}s)"
                )
            else:
                print(
                    f"Converting: {video.name} -> {gif_name} (couldn't get duration, using start)"
                )
        else:
            print(f"Converting: {video.name} -> {gif_name}")

        # FFmpeg two-pass GIF with palette optimization
        # -ss before -i for fast seeking
        # This produces much better quality than single-pass
        seek_opt = f"-ss {start_seconds} " if start_seconds > 0 else ""
        ffmpeg_cmd = (
            f'ffmpeg -y {seek_opt}-t {duration} -i "{video}" '
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


def _load_trim_metadata():
    """Load trim metadata from YAML files in demo-results/videos/.

    Returns dict mapping video filename to trim_start_seconds.
    """
    import yaml

    trim_times = {}
    demo_results = paths.FRONTEND_PATH / "demo-results" / "videos"

    # Look for all *.demo.yaml files
    if demo_results.exists():
        for yaml_file in demo_results.glob("*.demo.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                    if data:
                        for key, value in data.items():
                            if (
                                isinstance(value, dict)
                                and "video" in value
                                and "trim_start_seconds" in value
                            ):
                                trim_times[value["video"]] = float(
                                    value["trim_start_seconds"]
                                )
            except Exception as e:
                print(f"Warning: Failed to parse {yaml_file}: {e}")

    return trim_times


@task
def demo_trim(c, trim_start=None, auto=True):
    """Trim initial loading screen from demo videos.

    Removes the first N seconds from each video to eliminate the loading
    screen that appears while the page loads. Videos are replaced in place.

    By default, reads trim times from *.demo.yaml files generated by demo tests.
    Fall back to --trim-start if no YAML metadata found.

    Usage:
        inv demo.trim                    # Use auto-detected trim times from YAML
        inv demo.trim --trim-start 5     # Override: trim first 5 seconds from all
        inv demo.trim --no-auto          # Disable auto-detection, use default 3s

    Args:
        trim_start: Seconds to trim from beginning (overrides auto-detection)
        auto: If True, read trim times from *.demo.yaml files (default: True)

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

    # Load auto-detected trim times from YAML files
    trim_metadata = {}
    if auto and trim_start is None:
        trim_metadata = _load_trim_metadata()
        if trim_metadata:
            print(f"Found trim metadata for {len(trim_metadata)} videos:")
            for video, seconds in trim_metadata.items():
                print(f"  {video}: {seconds:.2f}s")
            print()

    # Default trim time if not specified and no metadata
    default_trim = trim_start if trim_start is not None else 3

    # Only process named demo videos
    videos = []
    for video_name in DEMO_VIDEO_NAMES:
        video_path = docs_videos / video_name
        if video_path.exists():
            videos.append(video_path)

    if not videos:
        print("No named demo videos found in docs/assets/videos/")
        print("Expected files: " + ", ".join(DEMO_VIDEO_NAMES))
        print("Run 'inv demo.create' first to record demo videos.")
        return

    print(f"Trimming {len(videos)} videos...\n")

    for video in videos:
        # Use per-video trim time from metadata, or default
        video_trim = trim_metadata.get(video.name, default_trim)
        video_duration = _get_video_duration(c, video)
        if not video_duration:
            print(f"  SKIPPED: {video.name} (couldn't get duration)")
            continue

        if video_duration <= video_trim:
            print(f"  SKIPPED: {video.name} (too short: {video_duration:.1f}s)")
            continue

        # Create temp file for output
        temp_path = video.with_suffix(".tmp.webm")

        print(
            f"Trimming: {video.name} ({video_duration:.1f}s -> {video_duration - video_trim:.1f}s, trim={video_trim:.2f}s)"
        )

        # FFmpeg: seek to video_trim and copy to new file
        # Using -c copy for fast processing (no re-encoding)
        ffmpeg_cmd = (
            f'ffmpeg -y -ss {video_trim} -i "{video}" ' f'-c copy "{temp_path}"'
        )

        result = c.run(ffmpeg_cmd, warn=True, hide=True)
        if result.ok:
            # Replace original with trimmed version
            temp_path.replace(video)
            new_size_kb = video.stat().st_size / 1024
            print(f"  Trimmed: {video.name} ({new_size_kb:.1f} KB)")
        else:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            print(f"  FAILED: {video.name}")
            print(
                f"  Error: {result.stderr[:200] if result.stderr else 'Unknown error'}"
            )

    print(f"\nTrimmed videos saved to: {docs_videos}")


@task
def demo_quick(c, duration=10, fps=12, width=400):
    """Record demos and create GIF previews in one step.

    Combines demo.create and demo.gifs for convenience.
    Creates both full videos and GIF previews from the middle of each video.

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


@task
def demo_snapshots(c):
    """Take site screenshots for documentation.

    Captures screenshots of key pages and saves to docs/assets/site_snapshots/.

    Pages captured:
    - Home page
    - Tournaments list
    - Tournament detail
    - Bracket view
    - Draft modal
    - HeroDraft view
    """
    print("=== Site Snapshots ===")

    # Reset demo_herodraft and generate bracket before taking screenshots
    reset_data = _reset_demo_data(c, "herodraft")
    if reset_data and reset_data.get("tournament_pk"):
        _generate_bracket(c, reset_data["tournament_pk"])

    flush_test_redis(c)
    _run_demo_in_docker(c, spec="Site Snapshots")
    _copy_demo_snapshots(c)


ns_demo.add_task(demo_create, "create")
ns_demo.add_task(demo_shuffle, "shuffle")
ns_demo.add_task(demo_snake, "snake")
ns_demo.add_task(demo_herodraft, "herodraft")
ns_demo.add_task(demo_snapshots, "snapshots")
ns_demo.add_task(demo_all, "all")
ns_demo.add_task(demo_gifs, "gifs")
ns_demo.add_task(demo_trim, "trim")
ns_demo.add_task(demo_quick, "quick")
ns_demo.add_task(demo_clean, "clean")

ns_test.add_collection(ns_demo, "demo")
