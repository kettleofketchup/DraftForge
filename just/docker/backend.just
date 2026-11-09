# Docker backend commands (backend and backend-dev images)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
registry := "ghcr.io/kettleofketchup/draftforge"

# Build backend (runtime) and backend-dev (runtime-dev); --push, --release (version tag on the prod image only)
[group('docker::backend')]
build *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    dev_flags=()
    for flag in "$@"; do
        if [[ "$flag" != --release ]]; then
            dev_flags+=("$flag")
        fi
    done
    {{just}} docker::buildx backend backend runtime backend/Dockerfile . "$@"
    {{just}} docker::buildx backend backend-dev runtime-dev backend/Dockerfile . ${dev_flags[@]+"${dev_flags[@]}"}

# Build and push backend images
[group('docker::backend')]
push:
    {{just}} docker::backend::build --push

# Pull backend and backend-dev by content hash
[group('docker::backend')]
pull:
    {{just}} docker::pull-image backend backend
    {{just}} docker::pull-image backend backend-dev

# Run the backend image interactively
[group('docker::backend')]
run:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' {{quote(root / "pyproject.toml")}} | head -n 1)
    exec docker run -it "{{registry}}/backend:$version"
