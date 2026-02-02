# Test database image commands

root := source_directory() / "../.."
image := "draftforge/test-db:latest"
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker::db')]
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    EXISTING=$(docker inspect --format='{{{{index .Config.Labels "org.draftforge.test-db.content-hash"}}' {{image}} 2>/dev/null || echo "")

    if [[ "$HASH" == "$EXISTING" ]]; then
        echo "Test DB image up-to-date (hash: ${HASH:0:12}...)"
        exit 0
    fi

    echo "Hash changed, rebuilding test DB..."
    # Run populate directly (not via just, to avoid circular dependency)
    {{inv}} db.populate.all

    # Build using temp context to avoid .dockerignore excluding sqlite files
    TMPDIR=$(mktemp -d)
    trap "rm -rf $TMPDIR" EXIT
    cp backend/test.db.sqlite3 "$TMPDIR/"
    cp docker/Dockerfile.test-db "$TMPDIR/Dockerfile"

    docker build "$TMPDIR" \
        --build-arg CONTENT_HASH="$HASH" \
        -t {{image}}
    echo "Built {{image}} (hash: ${HASH:0:12}...)"
