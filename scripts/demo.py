"""Demo video recording, trimming and GIF conversion (`just demo::*`).

Run from the repo root with the project venv:
    python -m scripts.demo <command> [options]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

import paths
from scripts.compose import base_url, flush_test_redis, playwright_env
from scripts.slots import SlotError

DEMO_VIDEO_NAMES = [
    "captain1_herodraft.webm",
    "captain2_herodraft.webm",
    "shuffle_draft.webm",
    "snake_draft.webm",
    "csv_import.webm",
    "event_creation.webm",
    "roll_call.webm",
]

# Per-video GIF start time overrides (seconds). Overrides start_from_middle.
GIF_START_OVERRIDES: dict[str, float] = {
    "csv_import.webm": 22,
}

DEMO_RESET_KEYS = {
    "herodraft": "demo_herodraft",
    "shuffle": "demo_shuffle_draft",
    "snake": "demo_snake_draft",
    "csv": "demo_csv_import",
}


@dataclass(frozen=True)
class Clip:
    """A short animated WebP cut side by side from recordings of one run."""

    output: str
    videos: tuple[str, ...]
    metadata: str
    key: str


# Cut from the raw recordings in demo-results/, whose clock the spec's
# timestamps use; docs/assets/videos/ copies may already be trimmed.
DEMO_CLIPS = [
    Clip(
        output="herodraft_chat.webp",
        videos=("captain1_herodraft.webm", "captain2_herodraft.webm"),
        metadata="herodraft.demo.yaml",
        key="chat_clip",
    ),
    Clip(
        output="herodraft_chat_picks.webp",
        videos=("captain1_herodraft.webm", "captain2_herodraft.webm"),
        metadata="herodraft.demo.yaml",
        key="chat_picks_clip",
    ),
]

DEMO_RESULTS = paths.FRONTEND_PATH / "demo-results"
DOCS_ASSETS = paths.PROJECT_PATH / "docs" / "assets"

FFMPEG_MISSING = """ERROR: FFmpeg is not installed.

Install FFmpeg:
  Ubuntu/Debian: sudo apt install ffmpeg
  macOS:         brew install ffmpeg
  Windows:       choco install ffmpeg"""


def reset_demo_data(demo_key: str) -> dict[str, Any] | None:
    reset_key = DEMO_RESET_KEYS.get(demo_key)
    if not reset_key:
        print(f"  Warning: No reset key for demo '{demo_key}'")
        return None

    url = f"{base_url()}/api/tests/demo/{reset_key}/reset/"
    print(f"  Resetting demo data: {reset_key}...")
    try:
        response = requests.post(url, verify=False, timeout=10)
    except requests.RequestException as e:
        print(f"  Reset failed: {e}")
        return None
    if not response.ok:
        print(f"  Reset failed: {response.status_code} - {response.text[:100]}")
        return None
    data: dict[str, Any] = response.json()
    print(f"  Reset successful: {data.get('tournament', 'unknown')}")
    return data


def generate_bracket(tournament_pk: int) -> bool:
    url = f"{base_url()}/api/tests/demo/bracket/{tournament_pk}/generate/"
    print(f"  Generating bracket for tournament {tournament_pk}...")
    try:
        response = requests.post(url, verify=False, timeout=10)
    except requests.RequestException as e:
        print(f"  Bracket generation failed: {e}")
        return False
    if not response.ok:
        print(
            f"  Bracket generation failed: {response.status_code} - {response.text[:100]}"
        )
        return False
    print("  Bracket generated successfully")
    return True


def run_demo(spec: str = "", workers: int = 1) -> int:
    flush_test_redis()
    pw_args = ["--config=playwright.demo.config.ts", f"--workers={workers}"]
    if spec:
        pw_args += ["--grep", spec]
    print(f"  Running: npx playwright test {' '.join(pw_args)}")
    # Returned, not raised: a failed run still leaves partial videos to copy.
    result = subprocess.run(
        ["npx", "playwright", "test", *pw_args],
        cwd=paths.FRONTEND_PATH,
        env={**os.environ, **playwright_env()},
    )
    if result.returncode != 0:
        print(f"  FAILED: playwright exited {result.returncode}", file=sys.stderr)
    return result.returncode


def copy_demo_videos() -> None:
    videos_dir = DEMO_RESULTS / "videos"
    docs_videos = DOCS_ASSETS / "videos"
    docs_videos.mkdir(parents=True, exist_ok=True)

    if not videos_dir.exists():
        print(f"  Warning: Video directory not found: {videos_dir}")
        return

    print("\nCopying demo videos to docs/assets/videos/...")
    copied = 0
    for name in DEMO_VIDEO_NAMES:
        video_file = videos_dir / name
        if video_file.exists():
            shutil.copy2(video_file, docs_videos / name)
            print(f"  Copied: {name}")
            copied += 1
    if copied == 0:
        print("  No named demo videos found. Check test output for errors.")
    else:
        print(f"\n{copied} demo videos saved to: {docs_videos}")
        print("Commit these videos to git for documentation.")


def copy_demo_snapshots() -> None:
    snapshots_dir = DEMO_RESULTS / "site_snapshots"
    docs_snapshots = DOCS_ASSETS / "site_snapshots"
    docs_snapshots.mkdir(parents=True, exist_ok=True)

    if not snapshots_dir.exists():
        print(f"  Warning: Snapshot directory not found: {snapshots_dir}")
        return

    print("\nCopying snapshots to docs/assets/site_snapshots/...")
    copied = 0
    for snapshot in snapshots_dir.glob("*.png"):
        shutil.copy2(snapshot, docs_snapshots / snapshot.name)
        print(f"  Copied: {snapshot.name}")
        copied += 1
    if copied == 0:
        print("  No snapshots found. Check test output for errors.")
    else:
        print(f"\n{copied} snapshots saved to: {docs_snapshots}")


def create(spec: str = "") -> int:
    print("=== Demo Recording ===")
    if spec:
        reset_demo_data(spec)
    else:
        for demo_key in DEMO_RESET_KEYS:
            reset_demo_data(demo_key)
    status = run_demo(spec=spec, workers=1)
    copy_demo_videos()
    return status


def _single(title: str, spec: str, reset_key: str | None = None) -> Callable[[], int]:
    def record() -> int:
        print(f"=== {title} ===")
        if reset_key:
            reset_demo_data(reset_key)
        status = run_demo(spec=spec)
        copy_demo_videos()
        return status

    return record


def _herodraft() -> int:
    status = _single("HeroDraft Demo", "herodraft", "herodraft")()
    return status or clips()


SINGLE_DEMOS: dict[str, Callable[[], int]] = {
    "shuffle": _single("Shuffle Draft Demo", "shuffle", "shuffle"),
    "snake": _single("Snake Draft Demo", "snake", "snake"),
    "herodraft": _herodraft,
    "csv": _single("CSV Import Demo", "CSV Import", "csv"),
    "event-creation": _single("Event Creation Demo", "event creation"),
    "roll-call": _single("Roll Call Demo", "roll call"),
}


def record_all() -> int:
    print("=== Recording All Demos ===")
    done: set[str] = set()
    for demo_key, reset_key in DEMO_RESET_KEYS.items():
        if reset_key not in done:
            reset_demo_data(demo_key)
            done.add(reset_key)
    status = run_demo(workers=1)
    copy_demo_videos()
    return status


def clean() -> None:
    if DEMO_RESULTS.exists():
        shutil.rmtree(DEMO_RESULTS)
        print(f"Cleaned: {DEMO_RESULTS}")


def video_duration(video_path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    out = result.stdout.strip()
    if result.returncode == 0 and out:
        try:
            return float(out)
        except ValueError:
            return None
    return None


def _named_videos() -> list[Path]:
    docs_videos = DOCS_ASSETS / "videos"
    videos = [docs_videos / n for n in DEMO_VIDEO_NAMES if (docs_videos / n).exists()]
    if not videos:
        print("No named demo videos found in docs/assets/videos/")
        print("Expected files: " + ", ".join(DEMO_VIDEO_NAMES))
        print("Run 'just demo::create' first to record demo videos.")
    return videos


def _ffmpeg_error(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr[:200] if result.stderr else "Unknown error"


def gifs(
    duration: int = 10, fps: int = 12, width: int = 400, start_from_middle: bool = True
) -> int:
    if not shutil.which("ffmpeg"):
        print(FFMPEG_MISSING)
        return 1

    docs_gifs = DOCS_ASSETS / "gifs"
    docs_gifs.mkdir(parents=True, exist_ok=True)
    videos = _named_videos()
    if not videos:
        return 0

    print(f"Converting {len(videos)} videos to GIFs...")
    print(f"  Duration: {duration}s, FPS: {fps}, Width: {width}px")
    print(f"  Start from middle: {start_from_middle}\n")

    failed = 0
    for video in videos:
        gif_path = docs_gifs / (video.stem + ".gif")
        start = 0.0
        if video.name in GIF_START_OVERRIDES:
            start = GIF_START_OVERRIDES[video.name]
            note = f" (from {start:.1f}s, override)"
        elif start_from_middle:
            total = video_duration(video)
            if total:
                start = max(0.0, (total - duration) / 2)
                note = f" (from {start:.1f}s)"
            else:
                note = " (couldn't get duration, using start)"
        else:
            note = ""
        print(f"Converting: {video.name} -> {gif_path.name}{note}")

        # Two-pass palette GIF; -ss before -i seeks fast.
        seek = ["-ss", str(start)] if start > 0 else []
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                *seek,
                "-t",
                str(duration),
                "-i",
                str(video),
                "-vf",
                f"fps={fps},scale={width}:-1:flags=lanczos,"
                "split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
                "[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                "-loop",
                "0",
                str(gif_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(
                f"  Created: {gif_path.name} ({gif_path.stat().st_size / 1024:.1f} KB)"
            )
        else:
            failed += 1
            print(f"  FAILED: {gif_path.name}")
            print(f"  Error: {_ffmpeg_error(result)}")

    print(f"\nGIFs saved to: {docs_gifs}")
    return 1 if failed else 0


def load_clip_window(clip: Clip) -> tuple[list[float], float] | None:
    """Per-video start offsets and the clip length, from the spec's metadata."""
    metadata = DEMO_RESULTS / "videos" / clip.metadata
    if not metadata.exists():
        return None
    try:
        data = yaml.safe_load(metadata.read_text())
    except (OSError, yaml.YAMLError) as e:
        print(f"Warning: Failed to parse {metadata}: {e}")
        return None
    window = data.get(clip.key) if isinstance(data, dict) else None
    if not isinstance(window, dict):
        return None
    try:
        starts = window["starts"]
        return [float(starts[v]) for v in clip.videos], float(
            window["duration_seconds"]
        )
    except (KeyError, TypeError, ValueError):
        return None


def clips(
    fps: int = 15,
    width: int = 1200,
    duration: float | None = None,
    quality: int = 80,
) -> int:
    """Cut each DEMO_CLIPS window into an animated WebP in docs/assets/gifs/."""
    if not shutil.which("ffmpeg"):
        print(FFMPEG_MISSING)
        return 1

    docs_gifs = DOCS_ASSETS / "gifs"
    docs_gifs.mkdir(parents=True, exist_ok=True)
    failed = 0
    for clip in DEMO_CLIPS:
        window = load_clip_window(clip)
        videos = [DEMO_RESULTS / "videos" / v for v in clip.videos]
        missing = [v.name for v in videos if not v.exists()]
        if window is None or missing:
            reason = (
                f"missing {', '.join(missing)}"
                if missing
                else f"no {clip.key} in {clip.metadata}"
            )
            print(f"  SKIPPED: {clip.output} ({reason}; record the demo first)")
            continue
        starts, length = window
        if duration is not None:
            length = duration
        out = docs_gifs / clip.output
        print(
            f"Clipping: {clip.output} ({length:.1f}s from {', '.join(f'{s:.1f}s' for s in starts)})"
        )

        inputs: list[str] = []
        for video, start in zip(videos, starts, strict=True):
            inputs += ["-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(video)]
        streams = "".join(f"[{i}:v]" for i in range(len(videos)))
        stack = f"{streams}hstack=inputs={len(videos)}," if len(videos) > 1 else ""
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                f"{stack}fps={fps},scale={width}:-2:flags=lanczos",
                "-an",
                "-c:v",
                "libwebp_anim",
                "-quality",
                str(quality),
                "-compression_level",
                "6",
                "-loop",
                "0",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  Created: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
        else:
            failed += 1
            print(f"  FAILED: {out.name}")
            print(f"  Error: {_ffmpeg_error(result)}")

    print(f"\nClips saved to: {docs_gifs}")
    return 1 if failed else 0


def load_trim_metadata() -> dict[str, float]:
    trim_times: dict[str, float] = {}
    videos_dir = DEMO_RESULTS / "videos"
    if not videos_dir.exists():
        return trim_times
    for yaml_file in videos_dir.glob("*.demo.yaml"):
        try:
            data = yaml.safe_load(yaml_file.read_text())
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: Failed to parse {yaml_file}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        for value in data.values():
            if (
                isinstance(value, dict)
                and "video" in value
                and "trim_start_seconds" in value
            ):
                trim_times[value["video"]] = float(value["trim_start_seconds"])
    return trim_times


def trim(trim_start: float | None = None, auto: bool = True) -> int:
    if not shutil.which("ffmpeg"):
        print(FFMPEG_MISSING)
        return 1

    metadata: dict[str, float] = {}
    if auto and trim_start is None:
        metadata = load_trim_metadata()
        if metadata:
            print(f"Found trim metadata for {len(metadata)} videos:")
            for video, seconds in metadata.items():
                print(f"  {video}: {seconds:.2f}s")
            print()

    default_trim = trim_start if trim_start is not None else 3.0
    videos = _named_videos()
    if not videos:
        return 0

    print(f"Trimming {len(videos)} videos...\n")
    failed = 0
    for video in videos:
        video_trim = metadata.get(video.name, default_trim)
        total = video_duration(video)
        if not total:
            print(f"  SKIPPED: {video.name} (couldn't get duration)")
            continue
        if total <= video_trim:
            print(f"  SKIPPED: {video.name} (too short: {total:.1f}s)")
            continue

        temp_path = video.with_suffix(".tmp.webm")
        print(
            f"Trimming: {video.name} ({total:.1f}s -> {total - video_trim:.1f}s, trim={video_trim:.2f}s)"
        )
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(video_trim),
                "-i",
                str(video),
                "-c",
                "copy",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            temp_path.replace(video)
            print(f"  Trimmed: {video.name} ({video.stat().st_size / 1024:.1f} KB)")
        else:
            failed += 1
            temp_path.unlink(missing_ok=True)
            print(f"  FAILED: {video.name}")
            print(f"  Error: {_ffmpeg_error(result)}")

    print(f"\nTrimmed videos saved to: {DOCS_ASSETS / 'videos'}")
    return 1 if failed else 0


def quick(duration: int = 10, fps: int = 12, width: int = 400) -> int:
    recorded = create()
    trimmed = trim()
    converted = gifs(duration=duration, fps=fps, width=width)
    clipped = clips()
    return recorded or trimmed or converted or clipped


def snapshots() -> int:
    print("=== Site Snapshots ===")
    reset = reset_demo_data("herodraft")
    if reset and reset.get("tournament_pk"):
        generate_bracket(reset["tournament_pk"])
    status = run_demo(spec="Site Snapshots")
    copy_demo_snapshots()
    return status


def _git_out(cmd: str) -> str | None:
    result = subprocess.run(
        cmd, shell=True, cwd=paths.PROJECT_PATH, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git_cleanup() -> int:
    """Rewrite history to drop old docs/assets/{videos,gifs} blobs (needs git-filter-repo)."""
    if not shutil.which("git-filter-repo"):
        print("ERROR: git-filter-repo is not installed.")
        print("")
        print("Install:")
        print("  pip install git-filter-repo")
        print("  # or: pipx install git-filter-repo")
        return 1

    video_dir = DOCS_ASSETS / "videos"
    gif_dir = DOCS_ASSETS / "gifs"
    count = _git_out(
        'git rev-list --all --objects -- "docs/assets/videos/" "docs/assets/gifs/" | wc -l'
    )
    blob_count = int(count) if count else 0
    if blob_count == 0:
        print("No demo video/GIF objects found in git history. Nothing to clean.")
        return 0

    size_mb = _git_out(
        "git rev-list --all --objects -- 'docs/assets/videos/' 'docs/assets/gifs/' "
        "| git cat-file --batch-check='%(objecttype) %(objectsize)' "
        "| grep blob | awk '{sum += $2} END {printf \"%.1f\", sum/1024/1024}'"
    )
    print(
        f"Found {blob_count} objects ({size_mb or '?'} MB) for demo videos/GIFs in git history."
    )
    print("")
    print("This will:")
    print("  1. Backup current demo files from the working tree")
    print("  2. Remove docs/assets/videos/ and docs/assets/gifs/ from all commits")
    print("  3. Restore the current demo files")
    print("  4. Create a fresh commit with the current versions")
    print("")
    print("After this, you must force-push all branches.")
    print("")

    if input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted.")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        backup_root = Path(tmp)
        print("\n1. Backing up current demo files...")
        for src_dir, name in [(video_dir, "videos"), (gif_dir, "gifs")]:
            if src_dir.exists():
                shutil.copytree(src_dir, backup_root / name)
                print(f"   Backed up {name}/")

        print("\n2. Rewriting git history (removing demo videos/GIFs)...")
        subprocess.run(
            [
                "git",
                "filter-repo",
                "--invert-paths",
                "--path",
                "docs/assets/videos/",
                "--path",
                "docs/assets/gifs/",
                "--force",
            ],
            cwd=paths.PROJECT_PATH,
            check=True,
        )

        print("\n3. Restoring current demo files...")
        for name, dst_dir in [("videos", video_dir), ("gifs", gif_dir)]:
            backup = backup_root / name
            if backup.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                for f in backup.iterdir():
                    shutil.copy2(f, dst_dir / f.name)
                print(f"   Restored {name}/")

        print("\n4. Committing restored files...")
        subprocess.run(
            ["git", "add", "docs/assets/videos/", "docs/assets/gifs/"],
            cwd=paths.PROJECT_PATH,
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "chore: re-add demo videos/GIFs after history cleanup",
            ],
            cwd=paths.PROJECT_PATH,
        )

    print("\nDone! History rewritten.")
    print("You must now force-push: git push --force-with-lease --all")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.demo")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("all", help="record every demo sequentially")
    create_p = sub.add_parser("create", help="record demos, optionally one --spec")
    create_p.add_argument("--spec", default="")
    for name in SINGLE_DEMOS:
        sub.add_parser(name)
    sub.add_parser("snapshots", help="take site screenshots")
    sub.add_parser("clean", help="delete frontend/demo-results/")
    sub.add_parser("git-cleanup", help="rewrite history to drop old demo blobs")

    gifs_p = sub.add_parser("gifs", help="convert demo videos to GIFs")
    quick_p = sub.add_parser("quick", help="create, trim, gifs, then clips")
    for sp in (gifs_p, quick_p):
        sp.add_argument("--duration", type=int, default=10)
        sp.add_argument("--fps", type=int, default=12)
        sp.add_argument("--width", type=int, default=400)
    gifs_p.add_argument(
        "--no-start-from-middle", dest="start_from_middle", action="store_false"
    )

    clips_p = sub.add_parser("clips", help="cut short animated WebP clips")
    clips_p.add_argument("--fps", type=int, default=15)
    clips_p.add_argument("--width", type=int, default=1200)
    clips_p.add_argument("--duration", type=float, default=None)
    clips_p.add_argument("--quality", type=int, default=80)

    trim_p = sub.add_parser("trim", help="trim the loading screen from demo videos")
    trim_p.add_argument("--trim-start", type=float, default=None)
    trim_p.add_argument("--no-auto", dest="auto", action="store_false")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parser().parse_args(argv)
    try:
        if ns.cmd == "all":
            return record_all()
        elif ns.cmd == "create":
            return create(ns.spec)
        elif ns.cmd in SINGLE_DEMOS:
            return SINGLE_DEMOS[ns.cmd]()
        elif ns.cmd == "snapshots":
            return snapshots()
        elif ns.cmd == "clean":
            clean()
        elif ns.cmd == "git-cleanup":
            return git_cleanup()
        elif ns.cmd == "gifs":
            return gifs(ns.duration, ns.fps, ns.width, ns.start_from_middle)
        elif ns.cmd == "clips":
            return clips(ns.fps, ns.width, ns.duration, ns.quality)
        elif ns.cmd == "trim":
            return trim(ns.trim_start, ns.auto)
        elif ns.cmd == "quick":
            return quick(ns.duration, ns.fps, ns.width)
    except SlotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"{exc.cmd[0]} failed (exit {exc.returncode})", file=sys.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
