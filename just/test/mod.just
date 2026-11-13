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

mod pw 'pw.just'
mod backend 'backend.just'
mod cicd 'cicd.just'
mod demo 'demo.just'
mod populate 'populate.just'

# Start this worktree's test stack in the foreground
[group('test')]
up:
    {{compose}} up --remove-orphans

# Start this worktree's test stack detached
[group('test')]
upd:
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
    if [[ -n "${1//[[:space:]]/}" ]]; then
        exec {{compose}} run --rm --entrypoint "" "$2" sh -c "$1"
    fi
    exec {{compose}} run --rm --entrypoint "" "$2"

# Stop the stack, update deps, build images, populate a fresh test DB, then start the stack detached
[group('test')]
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    # If worktree, ensure backend/.env is copied from main repo
    main_repo="$(git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
    if [[ -n "$main_repo" && "$main_repo" != "$PWD/.git" && "$main_repo" != "." ]]; then
        if [[ -f "$main_repo/backend/.env" && ! -f backend/.env ]]; then
            echo "Worktree detected — copying backend/.env from main repo..."
            cp "$main_repo/backend/.env" backend/.env
        fi
    fi

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

# The simulated dota_lobby for the 18-dota-lobby specs: just test::dota-lobby [up|down|restart|logs|ps]
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

# Slot helper unit tests (no containers)
[group('test')]
slots-unit *args:
    cd {{quote(root)}} && {{quote(python)}} -m pytest -p no:django -p no:cacheprovider scripts/slot_tests -q "$@"
