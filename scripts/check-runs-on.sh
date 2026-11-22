#!/usr/bin/env bash
# Guard which jobs may use the self-hosted `draftforge-home` runner label.
# Usage: scripts/check-runs-on.sh [workflows-dir]   (default .github/workflows)
#
# Fails (exit 1, one line per finding) when:
#   - the label appears in any job other than playwright.yml `prepare`, or outside a job;
#   - that job lacks `timeout-minutes`, or its `if` lacks any of the five allowlist
#     clauses below (compared with whitespace collapsed);
#   - a workflow using the label triggers on pull_request_target or workflow_run.
#
# This catches mistakes by trusted authors. It is not a security control: on
# pull_request GitHub runs the PR head's workflow, so a fork can edit this script too.
# The boundary is the home runner's job-started hook (home repo).
#
# Needs bash and mikefarah yq v4 (preinstalled on ubuntu-latest).
set -euo pipefail

label=draftforge-home
dir=${1:-.github/workflows}

clauses=(
    "vars.SELF_HOSTED_RUNNERS == 'true'"
    "github.event_name == 'pull_request'"
    "github.event.pull_request.head.repo.full_name == github.repository"
    "contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.event.pull_request.user.login))"
    "contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.triggering_actor))"
)

if ! command -v yq >/dev/null 2>&1 || ! yq --version 2>&1 | grep -q mikefarah; then
    echo "check-runs-on: needs mikefarah yq v4 on PATH" >&2
    exit 2
fi
if [[ ! -d "$dir" ]]; then
    echo "check-runs-on: $dir is not a directory" >&2
    exit 2
fi

findings=0
finding() {
    echo "$1"
    findings=$((findings + 1))
}

normalise() {
    tr -s '[:space:]' ' ' <<<"$1" | sed 's/^ //; s/ $//'
}

shopt -s nullglob
for file in "$dir"/*.yml "$dir"/*.yaml; do
    name=${file##*/}

    # Every string value mentioning the label, as "<top-level key> <job id>".
    if ! uses=$(yq ".. | select(tag == \"!!str\" and test(\"$label\")) | path | .[0] + \" \" + ((.[1] // \"\") | tostring)" "$file" 2>&1); then
        finding "$name: cannot parse: ${uses//$'\n'/ }"
        continue
    fi
    uses_label=0
    prepare_uses_label=0
    while read -r top job; do
        [[ -n "$top" ]] || continue
        uses_label=1
        if [[ "$top" != jobs || -z "$job" ]]; then
            finding "$name: $label outside a job (under $top)"
        elif [[ "$name" == playwright.yml && "$job" == prepare ]]; then
            prepare_uses_label=1
        else
            finding "$name: job $job uses $label; only playwright.yml job prepare may"
        fi
    done < <(sort -u <<<"$uses")

    if (( prepare_uses_label )); then
        if [[ "$(yq '.jobs.prepare | has("timeout-minutes")' "$file")" != true ]]; then
            finding "$name: job prepare uses $label without timeout-minutes"
        fi
        cond=$(normalise "$(yq '.jobs.prepare.if // ""' "$file")")
        for clause in "${clauses[@]}"; do
            if [[ "$cond" != *"$clause"* ]]; then
                finding "$name: job prepare if lacks: $clause"
            fi
        done
    fi

    if (( uses_label )); then
        # `on:` may be a string, a list or a map; the outer parentheses matter to yq.
        triggers=$(yq '.on | ((select(tag == "!!str")), (select(tag == "!!seq") | .[]), (select(tag == "!!map") | keys | .[]))' "$file")
        for bad in pull_request_target workflow_run; do
            if grep -qx "$bad" <<<"$triggers"; then
                finding "$name: uses $label and triggers on $bad"
            fi
        done
    fi
done

if (( findings )); then
    echo "check-runs-on: $findings finding(s)" >&2
    exit 1
fi
