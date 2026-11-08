# Docker release commands (production images, version-tagged)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Build the release images in parallel with version tags (--push to push). The backend recipe also builds backend-dev.
[group('docker::release')]
build *flags:
    {{just}} docker::parallel --release "$@" -- docker::backend::build docker::frontend::build-prod docker::nginx::build

# Build and push the release images
[group('docker::release')]
push:
    {{just}} docker::release::build --push

# Pull the production images (no -dev); a missing image warns but does not fail
[group('docker::release')]
pull:
    #!/usr/bin/env bash
    set -euo pipefail
    pids=()
    for service in backend frontend nginx; do
        {{just}} docker::pull-image "$service" "$service" &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || echo "Warning: a release image pull failed; continuing" >&2
    done
