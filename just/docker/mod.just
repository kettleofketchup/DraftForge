# Docker build and push commands

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
registry := "ghcr.io/kettleofketchup/draftforge"

mod backend 'backend.just'
mod frontend 'frontend.just'
mod nginx 'nginx.just'
mod release 'release.just'
mod db 'db.just'

# Build backend, frontend and nginx images in parallel (--push to push them)
[group('docker')]
all-build *flags:
    {{just}} docker::parallel "$@" -- docker::backend::build docker::frontend::build docker::nginx::build

# Build and push all images, plus the CI Playwright runner
[group('docker')]
all-push:
    {{just}} docker::parallel --push -- docker::backend::build docker::frontend::build docker::nginx::build docker::frontend::build-pw

# Pull all images (prod and -dev) by content hash, falling back to :latest; with DF_PW_CONTAINER=1 also the Playwright runner
[group('docker')]
all-pull:
    #!/usr/bin/env bash
    set -euo pipefail
    recipes=(docker::backend::pull docker::frontend::pull docker::nginx::pull)
    if [[ "${DF_PW_CONTAINER-}" == 1 ]]; then
        recipes+=(docker::frontend::pull-pw)
    fi
    {{just}} docker::parallel -- "${recipes[@]}"

# Output content hashes for Docker images
[group('docker')]
hash service="all":
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    if [[ "$1" == "all" ]]; then
        echo "frontend: $(./scripts/hash-docker-image.sh frontend | cut -c1-12)..."
        echo "playwright: $(./scripts/hash-docker-image.sh playwright | cut -c1-12)..."
        echo "backend:  $(./scripts/hash-docker-image.sh backend | cut -c1-12)..."
        echo "nginx:    $(./scripts/hash-docker-image.sh nginx | cut -c1-12)..."
    else
        ./scripts/hash-docker-image.sh "$1"
    fi

# docker buildx build one image: tags :latest and :<content-hash> (plus :<version> with --release); --push pushes, otherwise loads locally; --hash-only tags only :<content-hash> and leaves :buildcache alone (PR pushes)
[private]
buildx service image target dockerfile context *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    service=$1 image="{{registry}}/$2" target=$3 dockerfile=$4 context=$5
    push=false release=false hash_only=false
    for flag in "${@:6}"; do
        case "$flag" in
            --push) push=true ;;
            --release) release=true ;;
            --hash-only) hash_only=true ;;
            *) echo "docker: unknown option $flag (use --push, --release, --hash-only)" >&2; exit 2 ;;
        esac
    done
    if [[ "$hash_only" == true && "$release" == true ]]; then
        echo "docker: --hash-only and --release are exclusive" >&2
        exit 2
    fi
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)
    hash=$(./scripts/hash-docker-image.sh "$service")
    args=(--file "$dockerfile" --target "$target")
    if [[ "$hash_only" == false ]]; then
        args+=(--tag "$image:latest")
    fi
    if [[ "$release" == true ]]; then
        args+=(--tag "$image:$version")
    fi
    args+=(--tag "$image:$hash")
    # podman's buildx shim rejects BuildKit's type=registry cache syntax.
    registry_cache=true
    if docker --version 2>/dev/null | grep -qi podman; then
        registry_cache=false
    fi
    if [[ "$registry_cache" == true ]]; then
        args+=(--cache-from "type=registry,ref=$image:buildcache")
    fi
    if [[ "$push" == true ]]; then
        if [[ "$registry_cache" == true && "$hash_only" == false ]]; then
            args+=(--cache-to "type=registry,ref=$image:buildcache,mode=max")
        fi
        args+=(--push)
    else
        args+=(--load)
    fi
    if [[ "$registry_cache" == true ]]; then
        meta=$(mktemp)
        trap 'rm -f "$meta"' EXIT
        args+=(--metadata-file "$meta")
    fi
    echo "Running: docker buildx build ${args[*]} $context"
    start=$SECONDS
    docker buildx build "${args[@]}" "$context"
    if [[ "$registry_cache" == true ]]; then
        python3 -I scripts/buildx_timing.py --metadata-file "$meta" \
            --label "$2 ($target)" --seconds "$((SECONDS - start))" || true
    fi

# Pull <image>:<content-hash>, else :latest, and tag it :latest for compose
[private]
pull-image service image:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    image="{{registry}}/$2"
    hash=$(./scripts/hash-docker-image.sh "$1")
    echo "Pulling $image by hash (${hash:0:12}...)..."
    if docker pull -q "$image:$hash" >/dev/null 2>&1; then
        echo "  ✓ Found exact match for $image (hash: ${hash:0:12}...)"
        docker tag "$image:$hash" "$image:latest"
        exit 0
    fi
    echo "  Hash not found, trying $image:latest..."
    if docker pull -q "$image:latest" >/dev/null 2>&1; then
        echo "  ✓ Pulled $image:latest"
        exit 0
    fi
    echo "  ✗ No image available for $image" >&2
    exit 1

# Run just recipes in parallel and fail if any fails: parallel [flags...] -- recipe...
[private]
parallel *args:
    #!/usr/bin/env bash
    set -euo pipefail
    flags=()
    while [[ $# -gt 0 && "$1" != "--" ]]; do
        flags+=("$1")
        shift
    done
    if [[ $# -eq 0 ]]; then
        echo "docker::parallel: missing -- before the recipe list" >&2
        exit 2
    fi
    shift
    pids=()
    for recipe in "$@"; do
        {{just}} "$recipe" ${flags[@]+"${flags[@]}"} &
        pids+=("$!")
    done
    failed=0
    for i in "${!pids[@]}"; do
        if ! wait "${pids[$i]}"; then
            echo "✗ ${*:$((i + 1)):1} failed" >&2
            failed=1
        fi
    done
    exit "$failed"
