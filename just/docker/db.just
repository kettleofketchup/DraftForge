# Test database image commands

root := source_directory() / "../.."
image := "draftforge/test-db"
registry := "ghcr.io/kettleofketchup/draftforge/test-db"
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

# Output content hash for test-db sources
[group('docker::db')]
hash:
    #!/usr/bin/env bash
    cd {{root}}
    ./scripts/hash-test-db-sources.sh

# Build test-db image locally (skips if hash unchanged)
[group('docker::db')]
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    EXISTING=$(docker inspect --format='{{{{index .Config.Labels "org.draftforge.test-db.content-hash"}}' {{image}}:latest 2>/dev/null || echo "")

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
        -t {{image}}:latest \
        -t {{image}}:$HASH
    echo "Built {{image}} (hash: ${HASH:0:12}...)"

# Pull test-db image from GHCR (tries hash first, then latest)
[group('docker::db')]
pull:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    echo "Content hash: ${HASH:0:12}..."

    # Strategy 1: Try exact hash-tagged image (no migrations needed)
    if docker pull {{registry}}:$HASH 2>/dev/null; then
        echo "✓ Found exact match for hash ${HASH:0:12}..."
        docker tag {{registry}}:$HASH {{image}}:latest
        docker tag {{registry}}:$HASH {{image}}:$HASH
        exit 0
    fi

    # Strategy 2: Try latest
    echo "Hash-tagged image not found, trying latest..."
    if docker pull {{registry}}:latest 2>/dev/null; then
        echo "✓ Pulled latest image"
        docker tag {{registry}}:latest {{image}}:latest
        exit 0
    fi

    echo "✗ No test-db image available in registry"
    exit 1

# Push test-db image to GHCR (both hash and latest tags)
[group('docker::db')]
push:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)
    echo "Pushing test-db image (hash: ${HASH:0:12}...)"

    docker tag {{image}}:latest {{registry}}:$HASH
    docker push {{registry}}:$HASH

    docker tag {{image}}:latest {{registry}}:latest
    docker push {{registry}}:latest

    echo "Pushed:"
    echo "  - {{registry}}:$HASH"
    echo "  - {{registry}}:latest"
