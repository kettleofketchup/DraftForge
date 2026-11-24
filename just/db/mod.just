# Database commands (run on the host with the project venv)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
in_env := quote(root / "scripts/in-env.sh")
image := env("DF_TEST_DB_IMAGE", "draftforge/test-db")
# Where touch-dbs creates the sqlite files; the slot guard tests point it at a temp dir
db_dir := env("DF_DB_DIR", root / "backend")
# The slot guard tests point these at temp files
test_db := env("DF_TEST_DB_FILE", root / "backend/test.db.sqlite3")
slot_file := env("DF_SLOT_FILE", root / "docker/.env.slot")

# makemigrations takes an explicit app list (it does not read INSTALLED_APPS):
# add new Django apps here.
apps := "steam app bracket discordbot events org user lobby opsnotices league draft tournament"

mod migrate 'migrate.just'
mod populate 'populate.just'
mod avatars 'avatars.just'

# Run migrations for dev (same as db::migrate::dev)
[group('db')]
run-migrate:
    {{just}} db::migrate-env dev

# Create migrations with the dev env (default: every project app)
[group('db')]
makemigrations *names:
    {{just}} db::touch-dbs
    {{just}} db::manage dev makemigrations {{ if names == "" { apps } else { '"$@"' } }}

# Renumber this branch's migration onto main's after a max_migration.txt conflict
[group('db')]
rebase-migration app:
    {{just}} db::manage dev rebase_migration "$1"

# Run manage.py in backend/ with docker/.env.<stack> loaded and the cache off
[private]
manage stack *args:
    {{in_env}} "$1" backend env DISABLE_CACHE=true {{quote(python)}} manage.py "${@:2}"

# Make migrations, then migrate, for one env: dev, test, prod or release
[private]
migrate-env stack:
    {{just}} db::touch-dbs
    {{just}} db::manage "$1" makemigrations {{apps}}
    {{just}} db::manage "$1" migrate

[private]
touch-dbs:
    cd {{quote(db_dir)}} && mkdir -p data && touch -a test.db.sqlite3 dev.db.sqlite3 data/prod.db.sqlite3

[group('db')]
reset-test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    IMAGE="{{image}}:$HASH"
    if ! docker image inspect "$IMAGE" &>/dev/null; then
        echo "No test-db image for this worktree's sources ($IMAGE). Run 'just docker::db::build' first." >&2
        exit 1
    fi

    stopped=$({{just}} db::drop-test-db)
    trap '[[ -n "$stopped" ]] && echo "test DB not ready; $stopped left stopped (just test::compose start $stopped)" >&2' ERR
    echo "Extracting test database from cached image..."
    CONTAINER_NAME="test-db-extract-$$"
    docker create --name "$CONTAINER_NAME" "$IMAGE"
    docker cp "$CONTAINER_NAME:/data/test.db.sqlite3" {{quote(test_db)}}
    docker rm "$CONTAINER_NAME"
    echo "Restored {{test_db}}"
    read -ra stopped_services <<< "$stopped"
    {{just}} db::start-test-db-users "${stopped_services[@]}"

# Stop this worktree's slot services that hold the test DB open, then delete it with its WAL sidecars; prints the stopped services
[private]
drop-test-db:
    #!/usr/bin/env bash
    set -euo pipefail
    users=()
    if [[ -f {{quote(slot_file)}} ]]; then
        if ! out=$({{just}} test::compose ps --services --status running backend celery-worker); then
            echo "db: could not check whether this worktree's test slot has the test DB open; not replacing it" >&2
            exit 1
        fi
        read -ra users <<< "${out//$'\n'/ }"
    fi
    if (( ${#users[@]} )); then
        echo "Stopping ${users[*]} on this worktree's test slot while the test DB is replaced" >&2
        {{just}} test::compose stop "${users[@]}" >&2
    fi
    rm -f {{quote(test_db)}} {{quote(test_db + "-wal")}} {{quote(test_db + "-shm")}}
    echo "${users[*]}"

[private]
start-test-db-users *services:
    #!/usr/bin/env bash
    set -euo pipefail
    if (( $# )); then
        echo "Starting $* again"
        {{just}} test::compose start "$@"
    fi
