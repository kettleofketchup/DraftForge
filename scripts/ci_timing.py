#!/usr/bin/env python3
"""Collect GitHub Actions timing: queue waits, job/step durations, per-command
segments parsed from timestamped job logs (composite actions are only visible
there), and the per-layer buildx reports printed by scripts/buildx_timing.py.

Writes CSVs and summary.md to --out. Needs only python3 and an authenticated gh.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

REPO = "kettleofketchup/DraftForge"
TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z (.*)$")
SHARD_RE = re.compile(
    r"\s*\((?:shard )?\d+/\d+\)|\s*\((app|rest|migrations(?:-[a-z]+)?)\)"
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
BUILD_HEAD_RE = re.compile(
    r"── slowest build steps \(buildx (.+?)(?:: (\d+)m(\d+)s)?\) ──"
)
BUILD_STEP_RE = re.compile(r"^\s+(\d+(?:\.\d+)?)s  (.+)$")


def gh(path: str) -> str:
    return subprocess.run(
        ["gh", "api", path, "--allow-escape-sequences"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def gh_json(path: str) -> dict:
    return json.loads(gh(path))


def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s)


def secs(a: str | datetime | None, b: str | datetime | None) -> float | None:
    a = ts(a) if isinstance(a, str) else a
    b = ts(b) if isinstance(b, str) else b
    if a is None or b is None:
        return None
    return round((b - a).total_seconds(), 1)


def family(job_name: str) -> str:
    return SHARD_RE.sub("", job_name).strip()


def norm_cmd(cmd: str) -> str:
    cmd = ANSI_RE.sub("", cmd).strip()
    cmd = re.sub(r"--shard=\d+/\d+", "--shard=N", cmd)
    cmd = re.sub(r"\b(app|rest|migrations(?:-[a-z]+)?)\b(?=\)|$)", "<group>", cmd)
    return cmd[:110]


def parse_log(
    text: str, completed_at: str | None
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split a job log into segments at each `##[group]Run ...` marker and
    record intra-segment gaps of >=8s (where time actually goes)."""
    lines: list[tuple[datetime, str]] = []
    for raw in text.splitlines():
        m = TS_RE.match(raw.lstrip("\ufeff"))
        if m:
            lines.append((ts(m.group(1)), ANSI_RE.sub("", m.group(2))))
    if not lines:
        return [], [], []
    segs: list[dict] = []
    gaps: list[dict] = []
    builds: list[dict] = []
    build_label: str | None = None
    cur = {"name": "(runner init: image/provisioner/token)", "start": lines[0][0]}
    prev_t, prev_line = lines[0]
    for t, line in lines:
        if line.startswith("##[group]Run "):
            cur["end"] = t
            segs.append(cur)
            cur = {"name": norm_cmd(line[len("##[group]Run ") :]), "start": t}
        elif line.startswith("Post job cleanup.") and not cur["name"].startswith(
            "(post"
        ):
            cur["end"] = t
            segs.append(cur)
            cur = {"name": "(post-job cleanup)", "start": t}
        head = BUILD_HEAD_RE.search(line)
        if head:
            build_label = head.group(1)
            if head.group(2):
                builds.append(
                    {
                        "image": build_label,
                        "step": "(total)",
                        "dur_s": int(head.group(2)) * 60 + int(head.group(3)),
                    }
                )
        elif build_label:
            step = BUILD_STEP_RE.match(line)
            if step:
                builds.append(
                    {
                        "image": build_label,
                        "step": step.group(2)[:110],
                        "dur_s": float(step.group(1)),
                    }
                )
            else:
                build_label = None
        gap = (t - prev_t).total_seconds()
        if gap >= 8:
            gaps.append(
                {
                    "segment": cur["name"],
                    "gap_s": round(gap, 1),
                    "before": prev_line[:140],
                    "after": line[:140],
                }
            )
        prev_t, prev_line = t, line
    cur["end"] = ts(completed_at) or lines[-1][0]
    segs.append(cur)
    for s in segs:
        s["dur_s"] = round((s["end"] - s["start"]).total_seconds(), 1)
    return segs, gaps, builds


def collect(workflows: list[str], runs_per_wf: int, out: Path, with_logs: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    for wf in workflows:
        page = gh_json(
            f"repos/{REPO}/actions/workflows/{wf}/runs?status=completed&per_page=100"
        )
        picked = [
            r
            for r in page["workflow_runs"]
            if r["conclusion"] in ("success", "failure")
        ]
        runs += picked[:runs_per_wf]
        cancelled = sum(
            1 for r in page["workflow_runs"] if r["conclusion"] == "cancelled"
        )
        print(
            f"{wf}: {len(picked[:runs_per_wf])} runs picked; {cancelled}/{len(page['workflow_runs'])} of last page cancelled"
        )

    def jobs_for(run: dict) -> list[dict]:
        data = gh_json(f"repos/{REPO}/actions/runs/{run['id']}/jobs?per_page=100")
        for j in data["jobs"]:
            j["_run"] = run
        return data["jobs"]

    with ThreadPoolExecutor(8) as ex:
        all_jobs = [j for js in ex.map(jobs_for, runs) for j in js]

    job_rows, step_rows = [], []
    for j in all_jobs:
        r = j["_run"]
        job_rows.append(
            {
                "workflow": r["name"],
                "run_id": r["id"],
                "event": r["event"],
                "branch": r["head_branch"],
                "run_created": r["created_at"],
                "job_id": j["id"],
                "job": j["name"],
                "family": family(j["name"]),
                "conclusion": j["conclusion"],
                "runner": j.get("runner_name") or "",
                "labels": "|".join(j.get("labels") or []),
                "queue_s": secs(j["created_at"], j["started_at"]),
                "run_s": secs(j["started_at"], j["completed_at"]),
                "since_run_created_done_s": secs(r["created_at"], j["completed_at"]),
            }
        )
        for st in j.get("steps") or []:
            step_rows.append(
                {
                    "workflow": r["name"],
                    "run_id": r["id"],
                    "job_id": j["id"],
                    "family": family(j["name"]),
                    "n": st["number"],
                    "step": st["name"],
                    "conclusion": st["conclusion"],
                    "dur_s": secs(st.get("started_at"), st.get("completed_at")),
                }
            )

    seg_rows, gap_rows, build_rows = [], [], []
    if with_logs:

        def logs_for(j: dict) -> tuple[dict, str]:
            try:
                return j, gh(f"repos/{REPO}/actions/jobs/{j['id']}/logs")
            except subprocess.CalledProcessError:
                return j, ""

        with ThreadPoolExecutor(8) as ex:
            for j, text in ex.map(logs_for, all_jobs):
                segs, gaps, builds = parse_log(text, j["completed_at"])
                (out / "logs").mkdir(exist_ok=True)
                (out / "logs" / f"{j['id']}.log").write_text(text)
                for i, s in enumerate(segs):
                    seg_rows.append(
                        {
                            "workflow": j["_run"]["name"],
                            "run_id": j["_run"]["id"],
                            "job_id": j["id"],
                            "family": family(j["name"]),
                            "idx": i,
                            "segment": s["name"],
                            "dur_s": s["dur_s"],
                        }
                    )
                for b in builds:
                    build_rows.append(
                        {"workflow": j["_run"]["name"], "job_id": j["id"], **b}
                    )
                for g in gaps:
                    gap_rows.append(
                        {
                            "workflow": j["_run"]["name"],
                            "job_id": j["id"],
                            "family": family(j["name"]),
                            **g,
                        }
                    )

    for name, rows in [
        ("jobs", job_rows),
        ("steps", step_rows),
        ("segments", seg_rows),
        ("gaps", gap_rows),
        ("build_steps", build_rows),
    ]:
        if rows:
            with open(out / f"{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    summarize(job_rows, seg_rows, gap_rows, build_rows, runs, out)


def q(vals: list[float | None], p: float) -> float:
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return 0.0
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]


def summarize(
    jobs: list[dict],
    segs: list[dict],
    gaps: list[dict],
    builds: list[dict],
    runs: list[dict],
    out: Path,
) -> None:
    L: list[str] = ["# CI timing summary", ""]
    L.append(
        f"Runs analysed: {len(runs)}  |  jobs: {len(jobs)}  |  log segments: {len(segs)}\n"
    )

    L += [
        "## Run wall-clock (run created -> last job done)",
        "",
        "| workflow | runs | median min | p90 min |",
        "|---|---|---|---|",
    ]
    by_run: dict[tuple, float] = {}
    for j in jobs:
        k = (j["workflow"], j["run_id"])
        by_run[k] = max(by_run.get(k, 0), j["since_run_created_done_s"] or 0)
    per_wf = defaultdict(list)
    for (wf, _), v in by_run.items():
        per_wf[wf].append(v / 60)
    for wf, v in sorted(per_wf.items()):
        L.append(f"| {wf} | {len(v)} | {statistics.median(v):.1f} | {q(v, .9):.1f} |")

    L += [
        "",
        "## Per job family: queue vs run time (seconds)",
        "",
        "| workflow | family | n | queue med | queue p90 | run med | run p90 | runner-min total |",
        "|---|---|---|---|---|---|---|---|",
    ]
    fam = defaultdict(list)
    for j in jobs:
        fam[(j["workflow"], j["family"])].append(j)
    for (wf, f), js in sorted(
        fam.items(), key=lambda kv: -sum(x["run_s"] or 0 for x in kv[1])
    ):
        qs = [x["queue_s"] for x in js]
        rs = [x["run_s"] for x in js]
        L.append(
            f"| {wf} | {f} | {len(js)} | {q(qs,.5):.0f} | {q(qs,.9):.0f} | "
            f"{q(rs,.5):.0f} | {q(rs,.9):.0f} | {sum(r or 0 for r in rs)/60:.0f} |"
        )

    L += [
        "",
        "## Where the runner-time goes: segments aggregated across ALL jobs",
        "",
        "Sum of seconds over every job (i.e. cost repeated per job), with median per occurrence.",
        "",
        "| segment | occurrences | median s | p90 s | total runner-min | % of all |",
        "|---|---|---|---|---|---|",
    ]
    agg = defaultdict(list)
    for s in segs:
        agg[(s["workflow"], s["segment"])].append(s["dur_s"])
    grand = sum(s["dur_s"] for s in segs) or 1
    for (wf, name), v in sorted(agg.items(), key=lambda kv: -sum(kv[1]))[:45]:
        L.append(
            f"| `{name}` ({wf}) | {len(v)} | {statistics.median(v):.0f} | {q(v,.9):.0f} | "
            f"{sum(v)/60:.0f} | {100*sum(v)/grand:.1f}% |"
        )

    L += ["", "## Per-family segment medians (Playwright Tests)", ""]
    pf = defaultdict(lambda: defaultdict(list))
    order = defaultdict(dict)
    for s in segs:
        if s["workflow"] != "Playwright Tests":
            continue
        pf[s["family"]][s["segment"]].append(s["dur_s"])
        order[s["family"]].setdefault(s["segment"], s["idx"])
    for f in sorted(pf):
        L += [f"### {f}", "", "| # | segment | median s | p90 s |", "|---|---|---|---|"]
        for name in sorted(pf[f], key=lambda n: order[f][n]):
            v = pf[f][name]
            if statistics.median(v) >= 1:
                L.append(
                    f"| {order[f][name]} | `{name}` | {statistics.median(v):.0f} | {q(v,.9):.0f} |"
                )
        L.append("")

    L += [
        "## Biggest silent gaps inside steps (>=8s with no log output)",
        "",
        "| segment | n | median gap s | line before gap |",
        "|---|---|---|---|",
    ]
    ga = defaultdict(list)
    for g in gaps:
        ga[(g["segment"], g["before"][:80])].append(g["gap_s"])
    for (seg, before), v in sorted(ga.items(), key=lambda kv: -sum(kv[1]))[:30]:
        L.append(
            f"| `{seg[:50]}` | {len(v)} | {statistics.median(v):.0f} | `{before}` |"
        )

    L += ["", "## Slowest image build layers (from buildx_timing reports)", ""]
    if not builds:
        L.append("No buildx reports in these logs yet.")
    else:
        L += ["| image | step | n | median s | max s |", "|---|---|---|---|---|"]
        ba = defaultdict(list)
        for b in builds:
            ba[(b["image"], b["step"])].append(b["dur_s"])
        for (img, step), v in sorted(
            ba.items(), key=lambda kv: -statistics.median(kv[1])
        )[:30]:
            L.append(
                f"| {img} | `{step}` | {len(v)} | {statistics.median(v):.1f} | {max(v):.1f} |"
            )

    (out / "summary.md").write_text("\n".join(L) + "\n")
    print(f"wrote {out}/summary.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--workflows",
        nargs="+",
        default=[
            "playwright.yml",
            "build-test-db.yml",
            "preview-images.yml",
            "build-docker-images.yml",
            "frontend-format.yml",
            "changelog.yml",
        ],
    )
    ap.add_argument("--runs", type=int, default=12)
    ap.add_argument("--out", type=Path, default=Path(".ci-timing"))
    ap.add_argument("--no-logs", action="store_true")
    a = ap.parse_args()
    collect(a.workflows, a.runs, a.out, not a.no_logs)
