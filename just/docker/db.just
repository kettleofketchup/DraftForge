# Test database image commands

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
image := env("DF_TEST_DB_IMAGE", "draftforge/test-db")
registry := env("DF_TEST_DB_REGISTRY", "ghcr.io/kettleofketchup/draftforge/test-db")
ci_image := "ghcr.io/kettleofketchup/draftforge-ci/test-db"
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
# The slot guard tests point this at a temp file
test_db := env("DF_TEST_DB_FILE", root / "backend/test.db.sqlite3")

# Output content hash for test-db sources
[group('docker::db')]
hash:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}
    ./scripts/hash-test-db-sources.sh

# Build test-db image locally (skips if hash unchanged). --mode=pr --pr=<n> (home prepare job): always populates, then pushes only draftforge-ci/test-db:pr-<n>-<hash> through buildx
[group('docker::db')]
build *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}

    mode=trusted pr=""
    usage="use --mode=trusted|pr, --pr=<n>"
    for flag in "$@"; do
        case "$flag" in
            --mode=*) mode=${flag#--mode=} ;;
            --pr=*) pr=${flag#--pr=} ;;
            *) echo "docker::db: unknown option $flag ($usage)" >&2; exit 2 ;;
        esac
    done
    case "$mode" in
        trusted)
            if [[ -n "$pr" ]]; then
                echo "docker::db: --pr needs --mode=pr" >&2
                exit 2
            fi
            ;;
        pr)
            if [[ ! "$pr" =~ ^[0-9]+$ ]]; then
                echo "docker::db: --mode=pr needs a numeric --pr=<n>" >&2
                exit 2
            fi
            ;;
        *) echo "docker::db: unknown mode $mode ($usage)" >&2; exit 2 ;;
    esac

    HASH=$(./scripts/hash-test-db-sources.sh)

    if [[ "$mode" == pr ]]; then
        # The home runner has no Docker daemon: no image inspect, tag, push or plain
        # build, only the remote buildx builder. Never a draftforge/ tag or :latest.
        {{just}} db::populate::fresh
        CTX=$(mktemp -d)
        trap 'rm -rf "$CTX"' EXIT
        cp {{quote(test_db)}} "$CTX/test.db.sqlite3"
        cp docker/Dockerfile.test-db "$CTX/Dockerfile"
        tag="{{ci_image}}:pr-$pr-$HASH"
        docker buildx build --platform linux/amd64 --provenance=false \
            --build-arg CONTENT_HASH="$HASH" --tag "$tag" --push "$CTX"
        echo "Pushed $tag"
        exit 0
    fi

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
    cp {{quote(test_db)}} "$CTX/test.db.sqlite3"
    cp docker/Dockerfile.test-db "$CTX/Dockerfile"

    args=(--build-arg CONTENT_HASH="$HASH" -t "{{image}}:latest" -t "{{image}}:$HASH")
    # A docker-container buildx builder keeps the image in its cache unless loaded;
    # podman build always stores locally and rejects --load.
    if ! docker --version 2>/dev/null | grep -qi podman; then
        args+=(--load)
    fi
    docker build "${args[@]}" "$CTX"
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

# Push test-db image to GHCR (both hash and latest tags); --hash-only pushes only the hash tag (PR pushes)
[group('docker::db')]
[positional-arguments]
push *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{root}}
    hash_only=false
    for flag in "$@"; do
        case "$flag" in
            --hash-only) hash_only=true ;;
            *) echo "docker::db::push: unknown option $flag (use --hash-only)" >&2; exit 2 ;;
        esac
    done

    HASH=$(./scripts/hash-test-db-sources.sh)
    if ! docker image inspect "{{image}}:$HASH" >/dev/null 2>&1; then
        echo "✗ {{image}}:$HASH is missing; run 'just docker::db::build' first" >&2
        exit 1
    fi
    echo "Pushing test-db image (hash: ${HASH:0:12}...)"

    docker tag "{{image}}:$HASH" "{{registry}}:$HASH"
    docker push "{{registry}}:$HASH"
    echo "Pushed {{registry}}:$HASH"
    if [[ "$hash_only" == true ]]; then
        exit 0
    fi

    docker tag "{{image}}:$HASH" "{{registry}}:latest"
    docker push "{{registry}}:latest"
    echo "Pushed {{registry}}:latest"
