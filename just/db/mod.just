# Database commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

mod migrate 'migrate.just'
mod populate 'populate.just'

[group('db')]
run-migrate:
    {{inv}} db.migrate

[group('db')]
makemigrations *args:
    {{inv}} db.makemigrations {{args}}

[group('db')]
reset-test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    IMAGE="draftforge/test-db:latest"
    if ! docker image inspect "$IMAGE" &>/dev/null; then
        echo "No cached test-db image. Run 'just docker::db::build' first."
        exit 1
    fi

    echo "Extracting test database from cached image..."
    CONTAINER_NAME="test-db-extract-$$"
    docker create --name "$CONTAINER_NAME" "$IMAGE"
    docker cp "$CONTAINER_NAME:/data/test.db.sqlite3" backend/test.db.sqlite3
    docker rm "$CONTAINER_NAME"
    echo "Restored backend/test.db.sqlite3"
