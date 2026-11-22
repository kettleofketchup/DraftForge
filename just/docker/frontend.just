# Docker frontend commands (frontend, frontend-dev and playwright-runner images)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
registry := "ghcr.io/kettleofketchup/draftforge"

# Build the production and dev frontend images (--push to push)
[group('docker::frontend')]
build *flags:
    {{just}} docker::frontend::build-prod "$@"
    {{just}} docker::frontend::build-dev "$@"

# Build the production frontend image (runtime); --push, --release (adds the version tag), --no-cache, --mode=trusted|pr --pr=<n>
[group('docker::frontend')]
build-prod *flags:
    {{just}} docker::buildx frontend frontend runtime frontend/Dockerfile frontend "$@"

# Build the dev frontend image with Playwright (runtime-dev, slower); --push, --mode=trusted|pr --pr=<n>
[group('docker::frontend')]
build-dev *flags:
    {{just}} docker::buildx frontend frontend-dev runtime-dev frontend/Dockerfile frontend "$@"

# Build the CI Playwright runner image (frontend/Dockerfile.playwright: official Playwright image + node_modules); --push
[group('docker::frontend')]
build-pw *flags:
    {{just}} docker::buildx playwright playwright-runner runner frontend/Dockerfile.playwright frontend "$@"

# Build and push frontend images
[group('docker::frontend')]
push:
    {{just}} docker::frontend::build --push

# Pull frontend and frontend-dev by content hash
[group('docker::frontend')]
pull:
    {{just}} docker::pull-image frontend frontend
    {{just}} docker::pull-image frontend frontend-dev

# Pull the CI Playwright runner image by content hash
[group('docker::frontend')]
pull-pw:
    {{just}} docker::pull-image playwright playwright-runner

# Pull frontend-dev by content hash (the image the test stack runs)
[group('docker::frontend')]
pull-dev:
    {{just}} docker::pull-image frontend frontend-dev

# Run the frontend image interactively
[group('docker::frontend')]
run:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' {{quote(root / "pyproject.toml")}} | head -n 1)
    exec docker run -it "{{registry}}/frontend:$version"
