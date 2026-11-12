# Test database image commands

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "../..")
image := env("DF_TEST_DB_IMAGE", "draftforge/test-db")
registry := env("DF_TEST_DB_REGISTRY", "ghcr.io/kettleofketchup/draftforge/test-db")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Output content hash for test-db sources
[group('docker::db')]
hash:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}
    ./scripts/hash-test-db-sources.sh

# Build test-db image locally (skips if hash unchanged)
[group('docker::db')]
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    HASH=$(./scripts/hash-test-db-sources.sh)

    if docker image inspect "{{image}}:$HASH" >/dev/null 2>&1; then
        echo "Test DB image up-to-date (hash: ${HASH:0:12}...)"
        exit 0
    fi

    echo "Hash changed, rebuilding test DB..."
    # db::populate::fresh, not ::all: ::all builds this image
    {{just}} db::populate::fresh

    # Build using temp context to avoid .dockerignore excluding sqlite files
    CTX=$(mktemp -d)
    trap 'rm -rf "$CTX"' EXIT
    cp backend/test.db.sqlite3 "$CTX/"
    cp docker/Dockerfile.test-db "$CTX/Dockerfile"

    docker build "$CTX" \
        --build-arg CONTENT_HASH="$HASH" \
        -t "{{image}}:latest" \
        -t "{{image}}:$HASH"
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
    if docker pull "{{registry}}:$HASH" 2>/dev/null; then
        echo "✓ Found exact match for hash ${HASH:0:12}..."
        docker tag "{{registry}}:$HASH" "{{image}}:latest"
        docker tag "{{registry}}:$HASH" "{{image}}:$HASH"
        exit 0
    fi

    # Strategy 2: Try latest
    echo "Hash-tagged image not found, trying latest..."
    if docker pull "{{registry}}:latest" 2>/dev/null; then
        echo "✓ Pulled latest image"
        docker tag "{{registry}}:latest" "{{image}}:latest"
        PULLED=$(docker inspect --format='{{{{index .Config.Labels "org.draftforge.test-db.content-hash"}}' "{{registry}}:latest" 2>/dev/null || echo "")
        if [[ "$PULLED" == "$HASH" ]]; then
            docker tag "{{registry}}:latest" "{{image}}:$HASH"
        else
            echo "registry :latest is for hash ${PULLED:-<none>}, not $HASH; db::reset-test will refuse; run just docker::db::build"
        fi
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
    if ! docker image inspect "{{image}}:$HASH" >/dev/null 2>&1; then
        echo "✗ {{image}}:$HASH is missing; run 'just docker::db::build' first" >&2
        exit 1
    fi
    echo "Pushing test-db image (hash: ${HASH:0:12}...)"

    docker tag "{{image}}:$HASH" "{{registry}}:$HASH"
    docker push "{{registry}}:$HASH"

    docker tag "{{image}}:$HASH" "{{registry}}:latest"
    docker push "{{registry}}:latest"

    echo "Pushed:"
    echo "  - {{registry}}:$HASH"
    echo "  - {{registry}}:latest"
