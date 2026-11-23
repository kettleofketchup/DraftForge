#!/usr/bin/env bash
# Usage: scripts/pw-run-dir.sh <frontend-dir>
#
# Makes a results directory of its own for one local Playwright run and prints
# its absolute path: <frontend-dir>/test-results/runs/<UTC stamp>-<pid>. The
# run's artifacts, HTML report and run logs go under it (playwright.config.ts
# reads it from DF_PW_RUN_DIR), so concurrent runs in one worktree never
# clean each other's output. test-results/latest points at the newest run;
# runs past the newest DF_PW_KEEP_RUNS (default 20) are removed.
# DF_PW_RESULTS_DIR replaces <frontend-dir>/test-results (for the recipe tests).
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <frontend-dir>" >&2
    exit 2
fi

results=${DF_PW_RESULTS_DIR:-"$(cd "$1" && pwd)/test-results"}
runs="$results/runs"
keep=${DF_PW_KEEP_RUNS:-20}
id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$runs/$id"

# Swap the link with a rename so a reader never sees it missing.
tmp="$results/.latest.$$"
ln -sfn "runs/$id" "$tmp"
mv -Tf "$tmp" "$results/latest"

mapfile -t old < <(find "$runs" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r | tail -n +"$((keep + 1))")
for d in "${old[@]}"; do
    rm -rf "${runs:?}/$d"
done

echo "$runs/$id"
