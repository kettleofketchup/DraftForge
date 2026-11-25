# Playwright test commands (against this worktree's test stack slot)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
pw := just + " test::pw::run"
cicd := pw + " --grep @cicd"
pw_image := env("DF_PW_IMAGE", "ghcr.io/kettleofketchup/draftforge/playwright-runner:latest")

# npx playwright test <args> with DF_BASE_URL set for this slot, after flushing the test Redis (DF_PW_CONTAINER=1: inside the playwright-runner image, as CI does)
[group('test::pw')]
run *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    pw_env=$({{quote(python)}} -m scripts.compose env)
    eval "$pw_env"
    {{quote(python)}} -m scripts.compose flush-redis
    # Locally each run gets its own results dir, so a second run cannot wipe
    # the first one's output; CI keeps the flat test-results/ its uploads read.
    if [[ -z "${DF_PW_RUN_DIR-}" && -z "${CI-}" && "${GITHUB_ACTIONS-}" != true ]]; then
        DF_PW_RUN_DIR=$(scripts/pw-run-dir.sh frontend)
        echo "[pw] results: ${DF_PW_RUN_DIR#"$PWD/"} (frontend/test-results/latest)" >&2
    fi
    if [[ -n "${DF_PW_RUN_DIR-}" ]]; then
        export DF_PW_RUN_DIR
    fi
    cd frontend
    if [[ "${DF_PW_CONTAINER-}" != 1 ]]; then
        exec npx playwright test "$@"
    fi
    # Mounted at the same path so report and annotation paths match the checkout;
    # frontend/node_modules must resolve inside the image (CI links it to /app/node_modules).
    pass=(DF_BASE_URL DF_BASE_URL_SOURCE CI GITHUB_ACTIONS GITHUB_WORKSPACE
        PLAYWRIGHT_WORKERS PLAYWRIGHT_HEALTH_URL PLAYWRIGHT_CACHED_LEAGUES
        NAVBAR_SHOT_DIR DOTA_LOBBY_SIMULATOR_REQUIRED DF_PW_RUN_DIR)
    env_args=()
    for name in "${pass[@]}"; do
        env_args+=(-e "$name")
    done
    exec docker run --rm --network host --ipc host --entrypoint "" \
        --user "$(id -u):$(id -g)" -e HOME=/tmp "${env_args[@]}" \
        -v "$PWD:$PWD" -w "$PWD" {{quote(pw_image)}} \
        node_modules/.bin/playwright test "$@"

# All suites except demos (chromium, herodraft, events-sequential, dota-lobby-sequential, org-features-sequential)
[group('test::pw')]
headless *args:
    {{pw}} --project=chromium --project=herodraft --project=events-sequential --project=dota-lobby-sequential --project=org-features-sequential "$@"

[group('test::pw')]
ui:
    {{pw}} --ui

[group('test::pw')]
debug:
    {{pw}} --debug

# Specs under e2e/ by file (roll-call), path (events/roll-call) or directory (events), else any path containing it; no project dependencies
[group('test::pw')]
spec pattern *args:
    #!/usr/bin/env bash
    set -euo pipefail
    e2e=frontend/tests/playwright/e2e
    p=${1#./}
    shift
    p=${p#frontend/}
    p=${p#tests/playwright/}
    p=${p#e2e/}
    p=${p%/}
    p=${p%.spec.ts}
    mapfile -t specs < <(cd {{quote(root)}}/"$e2e" && find . -name '*.spec.ts' | sed 's|^\./||; s|\.spec\.ts$||' | LC_ALL=C sort)
    picked=()
    for s in "${specs[@]}"; do
        if [[ $s == "$p" || ${s##*/} == "$p" || $s == "$p"/* ]]; then
            picked+=("$s")
        fi
    done
    if (( ${#picked[@]} == 0 )); then
        for s in "${specs[@]}"; do
            [[ $s == *"$p"* ]] && picked+=("$s")
        done
    fi
    if (( ${#picked[@]} == 0 )); then
        echo "no spec under $e2e matches '$p'" >&2
        exit 1
    fi
    printf '[pw] spec: %s\n' "${picked[@]}" >&2
    filters=()
    for s in "${picked[@]}"; do
        filters+=("/\\/e2e\\/${s//\//\\/}\\.spec\\.ts\$/")
    done
    {{pw}} "${filters[@]}" --no-deps "$@"

[group('test::pw')]
file path *args:
    {{pw}} "$1" --no-deps "${@:2}"

# Tests whose title matches a pattern, without project dependencies
[group('test::pw')]
grep pattern *args:
    {{pw}} --grep "$1" --no-deps "${@:2}"

[group('test::pw')]
install:
    cd {{quote(root / "frontend")}} && npx playwright install

# The newest local run's HTML report (or one given: test-results/runs/<id>/report)
[group('test::pw')]
report dir="":
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root / "frontend")}}
    dir=$1
    if [[ -z "$dir" ]]; then
        dir=playwright-report
        [[ -d test-results/latest/report ]] && dir=test-results/latest/report
    fi
    exec npx playwright show-report "$dir"

[group('test::pw')]
navigation *args:
    {{pw}} tests/playwright/e2e/hydration-handling.spec.ts tests/playwright/e2e/navigation.spec.ts "$@"

[group('test::pw')]
tournament *args:
    {{pw}} tests/playwright/e2e/tournaments/ tests/playwright/e2e/tournament/ "$@"

[group('test::pw')]
draft *args:
    {{pw}} tests/playwright/e2e/draft/ tests/playwright/e2e/shuffle-draft/ "$@"

[group('test::pw')]
bracket *args:
    {{pw}} tests/playwright/e2e/bracket/ "$@"

[group('test::pw')]
league *args:
    {{pw}} tests/playwright/e2e/leagues/ "$@"

[group('test::pw')]
herodraft *args:
    {{pw}} tests/playwright/e2e/herodraft/ "$@"

# The dota-lobby specs. With this slot's simulator running
# (just test::dota-lobby up) they must use it: a skip is an error.
[group('test::pw')]
dota-lobby *args:
    {{just}} test::pw::with-simulator --project=dota-lobby-sequential --no-deps "$@"

[group('test::pw')]
all *args:
    {{pw}} "$@"

# Run only @cicd tagged tests (fast smoke tests for CI/CD)
[group('test::pw')]
cicd *args:
    {{cicd}} --project=chromium --project=mobile-pixel5 --project=mobile-iphone13 --project=mobile-iphone-se --project=herodraft --project=events-sequential --project=layout --project=dota-lobby-sequential --project=org-features-sequential --no-deps "$@"

# CI/CD per-project runners — used by the matrix shards in
# .github/workflows/playwright.yml. Local devs typically just use `cicd`.
[group('test::pw')]
cicd-chromium *args:
    {{cicd}} --project=chromium --no-deps "$@"

[group('test::pw')]
cicd-mobile *args:
    {{cicd}} --project=mobile-pixel5 --project=mobile-iphone13 --project=mobile-iphone-se --no-deps "$@"

[group('test::pw')]
cicd-layout *args:
    {{cicd}} --project=layout --no-deps "$@"

[group('test::pw')]
cicd-herodraft *args:
    {{cicd}} --project=herodraft --no-deps "$@"

# The events specs in order (events-sequential): they share one seeded event PK
[group('test::pw')]
cicd-events *args:
    {{cicd}} --project=events-sequential --no-deps "$@"

# The org-features specs in order (org-features-sequential): they share
# the seeded locked features orgs and reset them per test
[group('test::pw')]
cicd-org-features *args:
    {{cicd}} --project=org-features-sequential --no-deps "$@"

# The dota-lobby specs in order (dota-lobby-sequential): they share one
# simulated dota_lobby. Specs that need it skip unless `just test::dota-lobby up`
# ran, and then fail rather than skip when it never becomes available.
[group('test::pw')]
cicd-dota-lobby *args:
    {{just}} test::pw::with-simulator --grep @cicd --project=dota-lobby-sequential --no-deps "$@"

# Playwright with DOTA_LOBBY_SIMULATOR_REQUIRED=1 when this slot's simulated
# dota_lobby is running, unless the caller set it already.
[private]
with-simulator *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "${DOTA_LOBBY_SIMULATOR_REQUIRED-}" ]] \
        && [[ -n "$({{just}} test::compose ps --status running --quiet dota-lobby 2>/dev/null || true)" ]]; then
        export DOTA_LOBBY_SIMULATOR_REQUIRED=1
    fi
    exec {{pw}} "$@"

# Run the headless suite while streaming backend logs + health probes to
# the run's run-logs/ (frontend/test-results/latest/run-logs/) for diagnosing
# transient first-attempt timeouts. Combine with playwright's
# `trace: 'retain-on-failure'` and the health-probe reporter for full
# evidence on every failure.
[group('test::pw')]
headless-with-logs *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    if [[ -z "${DF_PW_RUN_DIR-}" ]]; then
        DF_PW_RUN_DIR=$(scripts/pw-run-dir.sh frontend)
    fi
    export DF_PW_RUN_DIR
    LOG_DIR="$DF_PW_RUN_DIR/run-logs"
    mkdir -p "$LOG_DIR"
    STAMP=$(date -u +"%Y%m%dT%H%M%SZ")
    BACKEND_LOG="$LOG_DIR/backend-$STAMP.log"
    echo "[run-logs] backend logs streaming to $BACKEND_LOG"
    {{quote(python)}} -m scripts.slots --root {{quote(root)}} compose logs -f --no-log-prefix --tail=0 backend > "$BACKEND_LOG" 2>&1 &
    LOG_PID=$!
    trap 'kill "$LOG_PID" 2>/dev/null || true' EXIT
    {{just}} test::pw::headless "$@"
