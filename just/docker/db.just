# Test database image commands

root := source_directory() / "../.."
image := "draftforge/test-db:latest"

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
    just db::populate::all
    docker build -f docker/Dockerfile.test-db \
        --build-arg CONTENT_HASH="$HASH" \
        -t {{image}} .
    echo "Built {{image}} (hash: ${HASH:0:12}...)"
