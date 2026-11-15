# Playwright test commands (against this worktree's test stack slot)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
pw := just + " test::pw::run"
cicd := pw + " --grep @cicd"

# npx playwright test <args> with DF_BASE_URL set for this slot, after flushing the test Redis
[group('test::pw')]
run *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    pw_env=$({{quote(python)}} -m scripts.compose env)
    eval "$pw_env"
    {{quote(python)}} -m scripts.compose flush-redis
    cd frontend
    exec npx playwright test "$@"

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

# Spec files whose path matches a pattern, without project dependencies
[group('test::pw')]
spec pattern *args:
    {{pw}} "$1" --no-deps "${@:2}"

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

[group('test::pw')]
report:
    cd {{quote(root / "frontend")}} && npx playwright show-report

[group('test::pw')]
navigation *args:
    {{pw}} tests/playwright/e2e/00-hydration-handling.spec.ts tests/playwright/e2e/01-navigation.spec.ts "$@"

[group('test::pw')]
tournament *args:
    {{pw}} tests/playwright/e2e/03-tournaments/ tests/playwright/e2e/04-tournament/ "$@"

[group('test::pw')]
draft *args:
    {{pw}} tests/playwright/e2e/07-draft/ tests/playwright/e2e/08-shuffle-draft/ "$@"

[group('test::pw')]
bracket *args:
    {{pw}} tests/playwright/e2e/09-bracket/ "$@"

[group('test::pw')]
league *args:
    {{pw}} tests/playwright/e2e/10-leagues/ "$@"

[group('test::pw')]
herodraft *args:
    {{pw}} tests/playwright/e2e/herodraft/ "$@"

# The 18-dota-lobby specs. With this slot's simulator running
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

# The 16-events specs in order (events-sequential): they share one seeded event PK
[group('test::pw')]
cicd-events *args:
    {{cicd}} --project=events-sequential --no-deps "$@"

# The 19-org-features specs in order (org-features-sequential): they share
# the seeded locked features orgs and reset them per test
[group('test::pw')]
cicd-org-features *args:
    {{cicd}} --project=org-features-sequential --no-deps "$@"

# The 18-dota-lobby specs in order (dota-lobby-sequential): they share one
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
# frontend/test-results/run-logs/ for diagnosing transient first-attempt
# timeouts. Combine with playwright's `trace: 'retain-on-failure'` and the
# health-probe reporter for full evidence on every failure.
[group('test::pw')]
headless-with-logs *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    LOG_DIR="frontend/test-results/run-logs"
    mkdir -p "$LOG_DIR"
    STAMP=$(date -u +"%Y%m%dT%H%M%SZ")
    BACKEND_LOG="$LOG_DIR/backend-$STAMP.log"
    echo "[run-logs] backend logs streaming to $BACKEND_LOG"
    {{quote(python)}} -m scripts.slots --root {{quote(root)}} compose logs -f --no-log-prefix --tail=0 backend > "$BACKEND_LOG" 2>&1 &
    LOG_PID=$!
    trap 'kill "$LOG_PID" 2>/dev/null || true' EXIT
    {{just}} test::pw::headless "$@"
