# Test environment commands (this worktree's test stack slot)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
in_env := quote(root / "scripts/in-env.sh")
slots := quote(python) + " -m scripts.slots --root " + quote(root)
compose := in_env + " - . " + slots + " compose"
slots_py := "cd " + quote(root) + " && " + slots
# The file ensure-db checks; the slot guard tests point it at a temp file
test_db := env("DF_TEST_DB_FILE", root / "backend/test.db.sqlite3")
# Where setup copies the main checkout's backend/.env; the slot guard tests point it at a temp file
backend_env := env("DF_BACKEND_ENV_FILE", root / "backend/.env")
limits := quote(root / "scripts/test-limits.sh")

mod pw 'pw.just'
mod backend 'backend.just'
mod cicd 'cicd.just'
mod demo 'demo.just'
mod populate 'populate.just'

# Make sure backend/test.db.sqlite3 exists and is non-empty (gitignored, so absent in a fresh worktree): pull the cached test-db image if needed, then extract it
[private]
ensure-db:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -s {{quote(test_db)}} ]]; then
        exit 0
    fi
    echo "backend/test.db.sqlite3 is missing or empty; providing it from the cached test-db image..."
    {{just}} docker::db::pull || echo "pull failed; building the test DB locally" >&2
    {{just}} db::populate::all

# Start this worktree's test stack in the foreground
[group('test')]
up: ensure-db
    {{limits}} apply
    {{compose}} up --remove-orphans

# Start this worktree's test stack detached
[group('test')]
upd: ensure-db
    {{limits}} apply
    {{compose}} up -d --remove-orphans

[group('test')]
down:
    {{compose}} down --remove-orphans

[group('test')]
logs:
    {{compose}} logs -f

[group('test')]
ps:
    {{compose}} ps

[group('test')]
restart:
    {{compose}} restart

[group('test')]
stop:
    {{compose}} stop

[group('test')]
build:
    {{compose}} build

[group('test')]
pull:
    {{compose}} pull

[group('test')]
top:
    {{compose}} top

# Run a shell command in a running test container: just test::exec backend 'python manage.py shell'
[group('test')]
exec service cmd:
    {{compose}} exec "$1" sh -c "$2"

# Run a one-off shell command in a new test container, bypassing the image entrypoint: just test::run 'python manage.py test app.tests -v 2'
[group('test')]
run cmd service="backend":
    #!/usr/bin/env bash
    set -euo pipefail
    {{limits}} apply
    procs=()
    if [[ "${GITHUB_ACTIONS-}" != true && -z "${CI-}" ]]; then
        procs=(-e "DJANGO_TEST_PROCESSES=${DJANGO_TEST_PROCESSES:-6}")
    fi
    if [[ -n "${1//[[:space:]]/}" ]]; then
        exec {{compose}} run --rm --entrypoint "" "${procs[@]}" "$2" sh -c "$1"
    fi
    exec {{compose}} run --rm --entrypoint "" "${procs[@]}" "$2"

# Show the shared CPU/memory cap on local tests and its current usage (DF_TEST_CPUS, DF_TEST_MEM; DF_TEST_LIMITS=0 disables)
[group('test')]
limits:
    {{limits}} show

# Stop the stack, update deps, build images, populate a fresh test DB, then start the stack detached
[group('test')]
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    # If worktree, ensure backend/.env is copied from main repo
    main_repo="$(git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
    if [[ -n "$main_repo" && "$main_repo" != "$PWD/.git" && "$main_repo" != "." ]]; then
        if [[ -f "$main_repo/backend/.env" && ! -f {{quote(backend_env)}} ]]; then
            echo "Worktree detected — copying backend/.env from main repo..."
            cp "$main_repo/backend/.env" {{quote(backend_env)}}
        fi
    fi

    {{limits}} apply
    # Allocate the slot before anything touches containers.
    allocated=$({{slots}} ensure)
    read -r _ slot _ <<< "$allocated"
    if (( slot >= 1 )); then
        echo "note: test::setup rebuilds the shared dev images every slot uses; other running slots pick them up on their next recreate"
    fi

    step=0
    total=5
    run_step() {
        local name=$1 start
        shift
        step=$((step + 1))
        echo "  [$step/$total] $name..."
        start=$SECONDS
        "$@"
        echo "  [$step/$total] $name $((SECONDS - start))s"
        echo
    }
    stop_stack() {
        {{in_env}} test . {{slots}} compose down --remove-orphans || echo "warning: stopping the test stack failed; continuing" >&2
    }
    start_stack() {
        {{in_env}} test . {{slots}} compose down
        {{in_env}} test . {{slots}} compose --ansi always up -d
    }

    echo
    echo "Test Setup ($total steps)"
    echo
    run_step "Stopping test stack" stop_stack
    run_step "Updating dependencies" {{just}} update::all-test
    run_step "Building Docker images" {{just}} docker::all-build
    run_step "Populating test database" {{just}} db::populate::fresh
    run_step "Starting test stack" start_stack
    echo "Test setup completed in ${SECONDS}s"

# Allocate (or re-adopt) this worktree's test slot and print it
[group('test')]
slot:
    {{slots_py}} print

# Show every slot reservation and df* project (read-only)
[group('test')]
slots:
    {{slots_py}} status

# Release this worktree's slot, or another idle one with --slot N
[group('test')]
slot-release *args:
    {{slots_py}} release "$@"

# Move this worktree to slot N
[group('test')]
slot-claim n:
    {{slots_py}} claim "$1"

# Tear down an orphaned df* project, or every slot idle past 12h with --stale
[group('test')]
slot-reap *args:
    {{slots_py}} reap "$@"

# Turn the Discord bot and celery beat on or off for this slot
[group('test')]
background state:
    {{slots_py}} background "$1"

# The simulated dota_lobby for the 22-dota-lobby specs: just test::dota-lobby [up|down|restart|logs|ps]
[group('test')]
dota-lobby action="up":
    #!/usr/bin/env bash
    set -euo pipefail
    case "$1" in
        # The whole stack with the profile on, not `up dota-lobby`: slots N >= 1
        # scale celery-beat and discord-bot to 0, which needs them in the selection.
        up) COMPOSE_PROFILES=dota-lobby exec {{compose}} up -d ;;
        down) exec {{compose}} rm --stop --force dota-lobby ;;
        restart) exec {{compose}} restart dota-lobby ;;
        logs) exec {{compose}} logs -f dota-lobby ;;
        ps) exec {{compose}} ps dota-lobby ;;
        *) echo "usage: just test::dota-lobby [up|down|restart|logs|ps]" >&2; exit 2 ;;
    esac

# Run compose against this worktree's slot (--stack S, --as-slot 0 for config)
[group('test')]
compose *args:
    {{compose}} "$@"

# Run only the tests this branch's changes reach (backend import graph + whole apps Django loads by name, `vitest related`); --plan only prints them. Iteration aid: the full suites still gate Verify and CI
[group('test')]
affected *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    run=--run
    pass=()
    for a in "$@"; do
        if [[ "$a" == --plan ]]; then run=; else pass+=("$a"); fi
    done
    exec {{quote(python)}} -m scripts.affected_tests $run "${pass[@]}"

# affected-tests selector unit tests (no containers)
[group('test')]
affected-unit *args:
    cd {{quote(root)}} && {{quote(python)}} -m pytest -p no:django -p no:cacheprovider scripts/test_affected_tests.py -q "$@"

# Slot helper unit tests (no containers)
[group('test')]
slots-unit *args:
    cd {{quote(root)}} && {{quote(python)}} -m pytest -p no:django -p no:cacheprovider scripts/slot_tests -q "$@"
