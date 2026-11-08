# Docker nginx commands

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
registry := "ghcr.io/kettleofketchup/draftforge"

# Build the nginx image; --push, --release (adds the version tag)
[group('docker::nginx')]
build *flags:
    {{just}} docker::buildx nginx nginx runtime nginx/Dockerfile nginx "$@"

# Build and push the nginx image
[group('docker::nginx')]
push:
    {{just}} docker::nginx::build --push

# Pull nginx by content hash
[group('docker::nginx')]
pull:
    {{just}} docker::pull-image nginx nginx

# Run the nginx image interactively
[group('docker::nginx')]
run:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' {{quote(root / "pyproject.toml")}} | head -n 1)
    exec docker run -it "{{registry}}/nginx:$version"
