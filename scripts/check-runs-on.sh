#!/usr/bin/env bash
# Guard which jobs can land on a self-hosted runner, the `draftforge-home` label in
# particular.
# Usage: scripts/check-runs-on.sh [workflows-dir]   (default .github/workflows)
#
# Fails (exit 1, one line per finding) when:
#   - a job's runs-on is anything but a literal GitHub-hosted label (ubuntu-*,
#     windows-*, macos-*), except playwright.yml `prepare`; an expression, a variable
#     (e.g. fromJSON(vars.X)), `self-hosted`, a label list with any other label, or a
#     runner group can all put a job on a self-hosted runner;
#   - playwright.yml `prepare.runs-on` is not exactly the guarded expression
#       ${{ (<guard>) && 'draftforge-home' || 'ubuntu-latest' }}
#     where <guard> is the five clauses below joined by ` && ` (whitespace collapsed),
#     or that job lacks `timeout-minutes`;
#   - a workflow that uses the label, or sets `env.HOME_PREPARE`, does not set it to
#     exactly ${{ <guard> }}, so the test jobs' idea of where prepare ran cannot drift
#     from its runs-on;
#   - the label appears anywhere other than that runs-on;
#   - a job calls a reusable workflow from another repository (its runs-on is not
#     checked here);
#   - a workflow that can run on the label triggers on pull_request_target or
#     workflow_run.
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
guard=${clauses[0]}
for clause in "${clauses[@]:1}"; do
    guard+=" && $clause"
done
want_runs_on="\${{ ($guard) && '$label' || 'ubuntu-latest' }}"
want_home_prepare="\${{ $guard }}"
hosted='^(ubuntu|windows|macos)-[A-Za-z0-9.-]+$'

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

    # Every string value mentioning the label, as its path joined by spaces.
    if ! uses=$(yq ".. | select(tag == \"!!str\" and test(\"$label\")) | path | map(tostring) | join(\" \")" "$file" 2>&1); then
        finding "$name: cannot parse: ${uses//$'\n'/ }"
        continue
    fi
    may_use_label=0
    while read -r where; do
        [[ -n "$where" ]] || continue
        if [[ "$name" == playwright.yml && "$where" == "jobs prepare runs-on" ]]; then
            may_use_label=1
        else
            finding "$name: $label at $where; only playwright.yml jobs.prepare.runs-on may name it"
        fi
    done < <(sort -u <<<"$uses")

    # One line per job: <id> <YAML tag of runs-on> (empty or !!null when absent).
    while read -r job kind; do
        [[ -n "$job" ]] || continue
        if [[ -z "$kind" || "$kind" == '!!null' ]]; then
            target=$(yq ".jobs[\"$job\"].uses // \"\"" "$file")
            if [[ -n "$target" && "$target" != ./* ]]; then
                finding "$name: job $job calls reusable workflow $target from another repository"
            fi
            continue
        fi
        if [[ "$name" == playwright.yml && "$job" == prepare ]]; then
            got=$(normalise "$(yq '.jobs.prepare["runs-on"] | select(tag == "!!str")' "$file")")
            if [[ "$got" != "$want_runs_on" ]]; then
                finding "$name: job prepare runs-on is not the guarded expression: $want_runs_on"
            fi
            if [[ "$(yq '.jobs.prepare | has("timeout-minutes")' "$file")" != true ]]; then
                finding "$name: job prepare has no timeout-minutes"
            fi
            continue
        fi
        case "$kind" in
            '!!str') labels=$(yq ".jobs[\"$job\"][\"runs-on\"]" "$file") ;;
            '!!seq') labels=$(yq ".jobs[\"$job\"][\"runs-on\"][]" "$file") ;;
            *)
                finding "$name: job $job runs-on is a runner group or map; use a GitHub-hosted label"
                continue
                ;;
        esac
        while IFS= read -r one; do
            if [[ ! "$one" =~ $hosted ]]; then
                finding "$name: job $job runs-on '$one' is not a literal GitHub-hosted label"
            fi
        done <<<"$labels"
    done < <(yq '.jobs // {} | to_entries | .[] | .key + " " + (.value["runs-on"] | tag)' "$file")

    if (( may_use_label )) || [[ "$(yq '.env | has("HOME_PREPARE")' "$file")" == true ]]; then
        got=$(normalise "$(yq '.env.HOME_PREPARE // ""' "$file")")
        if [[ "$got" != "$want_home_prepare" ]]; then
            finding "$name: env.HOME_PREPARE is not the runs-on guard: $want_home_prepare"
        fi
    fi

    if (( may_use_label )); then
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
