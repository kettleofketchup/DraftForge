# Database commands (run on the host with the project venv)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
in_env := quote(root / "scripts/in-env.sh")
image := env("DF_TEST_DB_IMAGE", "draftforge/test-db")

# makemigrations takes an explicit app list (it does not read INSTALLED_APPS):
# add new Django apps here.
apps := "steam app bracket discordbot events org user lobby"

mod migrate 'migrate.just'
mod populate 'populate.just'

# Run migrations for dev (same as db::migrate::dev)
[group('db')]
run-migrate:
    {{just}} db::migrate-env dev

# Create migrations with the dev env (default: every project app)
[group('db')]
makemigrations *names:
    {{just}} db::touch-dbs
    {{just}} db::manage dev makemigrations {{ if names == "" { apps } else { '"$@"' } }}

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
    cd {{quote(root / "backend")}} && touch -a test.db.sqlite3 dev.db.sqlite3 prod.db.sqlite3

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

    echo "Extracting test database from cached image..."
    CONTAINER_NAME="test-db-extract-$$"
    docker create --name "$CONTAINER_NAME" "$IMAGE"
    docker cp "$CONTAINER_NAME:/data/test.db.sqlite3" backend/test.db.sqlite3
    docker rm "$CONTAINER_NAME"
    echo "Restored backend/test.db.sqlite3"
