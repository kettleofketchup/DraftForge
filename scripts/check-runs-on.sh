#!/usr/bin/env bash
# Guard which jobs can land on a self-hosted runner, the home labels in particular:
# `draftforge-home` (the small jobs) and `draftforge-home-prepare` (playwright.yml
# `prepare` alone, so a burst of small jobs cannot hold it up).
# Usage: scripts/check-runs-on.sh [workflows-dir]   (default .github/workflows)
#
# Only the (workflow file, job id) pairs in `allowed` below may name a home label, and
# each only its own. Fails (exit 1, one line per finding) when:
#   - a job's runs-on is anything but a literal GitHub-hosted label (ubuntu-*,
#     windows-*, macos-*), unless the job is allowlisted; an expression, a variable
#     (e.g. fromJSON(vars.X)), a matrix value, `self-hosted`, a label list with any
#     other label, or a runner group can all put a job on a self-hosted runner;
#   - an allowlisted job's runs-on is not exactly the guarded expression
#       ${{ (<guard>) && '<its label>' || 'ubuntu-latest' }}
#     where <guard> is the five clauses below joined by ` && ` (whitespace collapsed)
#     and <its label> is the one the allowlist gives it (so prepare on
#     `draftforge-home`, or a small job on `draftforge-home-prepare`, fails), or that
#     job lacks `timeout-minutes`, or the allowlisted job no longer exists;
#   - playwright.yml, or any workflow that sets `env.HOME_PREPARE`, does not set it to
#     exactly ${{ <guard> }}, so the test jobs' idea of where prepare ran cannot drift
#     from its runs-on;
#   - either label appears anywhere other than an allowlisted job's runs-on;
#   - a job calls a reusable workflow from another repository (its runs-on is not
#     checked here);
#   - a workflow with an allowlisted job triggers on pull_request_target,
#     workflow_run or issues (the runner's hook refuses those events anyway).
#
# This catches mistakes by trusted authors. It is not a security control: on
# pull_request GitHub runs the PR head's workflow, so a fork can edit this script too.
# The boundary is the home runner's job-started hook (home repo).
#
# Needs bash and mikefarah yq v4 (preinstalled on ubuntu-latest; the runs-on-guard job
# installs a pinned copy so it also runs on the home runner).
set -euo pipefail

small_label=draftforge-home
prepare_label=draftforge-home-prepare
# Matches both labels (the prepare label starts with the small one).
any_label=draftforge-home
dir=${1:-.github/workflows}

# Jobs that may run on a home runner, as <file>:<job>=<label>: `prepare` on its own
# lane, and small jobs that relieve the hosted queue. Keep
# docs/development/ci-runners.md in step.
allowed=(
    "playwright.yml:prepare=$prepare_label"
    "unit-tests.yml:typecheck=$small_label"
    "changelog.yml:changelog=$small_label"
    "shellcheck.yml:shellcheck=$small_label"
    "shellcheck.yml:runs-on-guard=$small_label"
    "frontend-format.yml:prettier=$small_label"
    "frontend-shadcn-lint.yml:shadcn-lint=$small_label"
    "pr-labeler.yml:label=$small_label"
)
# The workflow whose env.HOME_PREPARE mirrors prepare's runs-on.
prepare_file=playwright.yml

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
want_runs_on() {
    echo "\${{ ($guard) && '$1' || 'ubuntu-latest' }}"
}
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

# Prints the label allowlisted for file $1, job $2; fails when the job is not listed.
allowed_label() {
    local entry
    for entry in "${allowed[@]}"; do
        if [[ "${entry%=*}" == "$1:$2" ]]; then
            echo "${entry##*=}"
            return 0
        fi
    done
    return 1
}

# Every allowlisted job must exist, so a renamed job cannot leave a stale entry behind.
for entry in "${allowed[@]}"; do
    pair=${entry%=*}
    file=$dir/${pair%%:*}
    job=${pair#*:}
    if [[ ! -f "$file" ]] || [[ "$(yq ".jobs | has(\"$job\")" "$file" 2>/dev/null)" != true ]]; then
        finding "${pair%%:*}: allowlisted job $job does not exist; update the allowlist in check-runs-on.sh"
    fi
done

shopt -s nullglob
for file in "$dir"/*.yml "$dir"/*.yaml; do
    name=${file##*/}

    # Every string value mentioning a home label, as <names the prepare label: true or
    # false><TAB><path joined by spaces>.
    if ! uses=$(yq ".. | select(tag == \"!!str\" and test(\"$any_label\")) | (test(\"$prepare_label\") | tostring) + \"\t\" + (path | map(tostring) | join(\" \"))" "$file" 2>&1); then
        finding "$name: cannot parse: ${uses//$'\n'/ }"
        continue
    fi
    while IFS=$'\t' read -r is_prepare where; do
        [[ -n "$where" ]] || continue
        found=$small_label
        [[ "$is_prepare" == true ]] && found=$prepare_label
        # The allowlisted job's runs-on is checked against its own label below.
        if [[ "$where" =~ ^jobs\ ([^ ]+)\ runs-on$ ]] && allowed_label "$name" "${BASH_REMATCH[1]}" >/dev/null; then
            continue
        fi
        finding "$name: $found at $where; only allowlisted jobs' runs-on may name it (scripts/check-runs-on.sh)"
    done < <(sort -u <<<"$uses")

    file_label=
    # One line per job: <id> <YAML tag of runs-on> (empty or !!null when absent).
    while read -r job kind; do
        [[ -n "$job" ]] || continue
        if job_label=$(allowed_label "$name" "$job"); then
            file_label=${file_label:-$job_label}
            want=$(want_runs_on "$job_label")
            got=$(normalise "$(yq ".jobs[\"$job\"][\"runs-on\"] | select(tag == \"!!str\")" "$file")")
            if [[ "$got" != "$want" ]]; then
                finding "$name: job $job runs-on is not the guarded expression for $job_label: $want"
            fi
            if [[ "$(yq ".jobs[\"$job\"] | has(\"timeout-minutes\")" "$file")" != true ]]; then
                finding "$name: job $job has no timeout-minutes"
            fi
            continue
        fi
        if [[ -z "$kind" || "$kind" == '!!null' ]]; then
            target=$(yq ".jobs[\"$job\"].uses // \"\"" "$file")
            if [[ -n "$target" && "$target" != ./* ]]; then
                finding "$name: job $job calls reusable workflow $target from another repository"
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

    if [[ "$name" == "$prepare_file" ]] || [[ "$(yq '.env | has("HOME_PREPARE")' "$file")" == true ]]; then
        got=$(normalise "$(yq '.env.HOME_PREPARE // ""' "$file")")
        if [[ "$got" != "$want_home_prepare" ]]; then
            finding "$name: env.HOME_PREPARE is not the runs-on guard: $want_home_prepare"
        fi
    fi

    if [[ -n "$file_label" ]]; then
        # `on:` may be a string, a list or a map; the outer parentheses matter to yq.
        triggers=$(yq '.on | ((select(tag == "!!str")), (select(tag == "!!seq") | .[]), (select(tag == "!!map") | keys | .[]))' "$file")
        for bad in pull_request_target workflow_run issues; do
            if grep -qx "$bad" <<<"$triggers"; then
                finding "$name: has a job allowed on $file_label and triggers on $bad"
            fi
        done
    fi
done

if (( findings )); then
    echo "check-runs-on: $findings finding(s)" >&2
    exit 1
fi
