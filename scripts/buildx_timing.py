#!/usr/bin/env python3
"""Report the slowest BuildKit steps of a finished `docker buildx build`.

Reads the build ref from a --metadata-file, replays the record with
`docker buildx history logs`, and prints the slowest steps plus how many were
cached. On GitHub Actions it also adds a ::notice and a job-summary table.
Never fails: the build it reports on has already succeeded.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VERTEX_RE = re.compile(r"^#(\d+) (.*)$")
DONE_RE = re.compile(r"^DONE (\d+(?:\.\d+)?)s$")
STATUS_RE = re.compile(r"^(CACHED|ERROR|CANCELED|WARN|WARNING|DONE)\b")
PROGRESS_RE = re.compile(r"^\d")


@dataclass
class Step:
    vertex: int
    name: str
    seconds: float | None = None
    cached: bool = False


def parse_history_log(text: str) -> list[Step]:
    """Join each vertex's name line with its DONE/CACHED line by vertex id.

    BuildKit's plain log prints the name ("#12 [builder 3/7] RUN npm ci") and the
    duration ("#12 DONE 41.3s") on different lines, with progress output
    (prefixed by elapsed seconds) in between.
    """
    steps: dict[int, Step] = {}
    for line in text.splitlines():
        m = VERTEX_RE.match(line.rstrip())
        if not m:
            continue
        vid, rest = int(m.group(1)), m.group(2).strip()
        step = steps.get(vid)
        done = DONE_RE.match(rest)
        if done:
            if step is None:
                step = steps[vid] = Step(vid, f"#{vid}")
            step.seconds = float(done.group(1))
        elif rest == "CACHED":
            if step is None:
                step = steps[vid] = Step(vid, f"#{vid}")
            step.cached = True
        elif step is None and not STATUS_RE.match(rest) and not PROGRESS_RE.match(rest):
            steps[vid] = Step(vid, re.sub(r"\s+", " ", rest))
    return sorted(steps.values(), key=lambda s: s.vertex)


def build_ref(metadata_file: Path) -> str | None:
    try:
        return json.loads(metadata_file.read_text()).get("buildx.build.ref") or None
    except (OSError, ValueError):
        return None


def history_log(ref: str) -> str | None:
    builder, _, record = ref.rpartition("/")
    builder = builder.split("/")[0]
    # history logs writes to stderr, and defaults to the default builder, not the one
    # that ran the build.
    proc = subprocess.run(
        ["docker", "buildx", "history", "logs", "--builder", builder, record],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout + proc.stderr


def fmt_duration(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}m{whole % 60:02d}s"


def render(
    label: str, total: float | None, steps: list[Step], top: int
) -> tuple[str, str]:
    timed = sorted(
        (s for s in steps if s.seconds is not None and not s.cached),
        key=lambda s: -(s.seconds or 0),
    )
    cached = sum(1 for s in steps if s.cached)
    head = f"buildx {label}" + (f": {fmt_duration(total)}" if total is not None else "")
    text = [f"── slowest build steps ({head}) ──"]
    md = [f"### ⏱ {head}", "", "| seconds | step |", "|---:|---|"]
    for s in timed[:top]:
        name = s.name if len(s.name) <= 110 else s.name[:109] + "…"
        text.append(f"  {s.seconds:7.1f}s  {name}")
        md.append(f"| {s.seconds:.1f} | `{name.replace('|', '¦')}` |")
    text.append(f"  … plus {cached} cached step(s)")
    md += ["", f"{cached} cached step(s).", ""]
    return "\n".join(text), "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata-file", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument(
        "--seconds", type=float, default=None, help="wall time of the build"
    )
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument(
        "--log",
        type=Path,
        default=None,
        help="parse this log instead of buildx history",
    )
    a = ap.parse_args(argv)

    if a.log is not None:
        log: str | None = a.log.read_text()
    else:
        ref = build_ref(a.metadata_file)
        log = history_log(ref) if ref else None
        if log is None:
            print(f"(no build-step report for {a.label}: ref={ref or 'unset'})")
            return 0

    text, md = render(a.label, a.seconds, parse_history_log(log), a.top)
    # One write, so reports from builds run in parallel do not interleave.
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if a.seconds is not None:
            print(f"::notice title=buildx {a.label}::{fmt_duration(a.seconds)}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(md + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - a report must never fail the build
        print(f"(build-step report failed: {exc})")
        sys.exit(0)
