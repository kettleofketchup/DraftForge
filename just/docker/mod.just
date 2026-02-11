# Docker build and push commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

mod backend 'backend.just'
mod frontend 'frontend.just'
mod nginx 'nginx.just'
mod release 'release.just'
mod db 'db.just'

[group('docker')]
all-build:
    {{inv}} docker.all.build

[group('docker')]
all-push:
    {{inv}} docker.all.push

[group('docker')]
all-pull:
    {{inv}} docker.all.pull

# Output content hashes for Docker images
[group('docker')]
hash service="all":
    #!/usr/bin/env bash
    cd {{root}}
    if [[ "{{service}}" == "all" ]]; then
        echo "frontend: $(./scripts/hash-docker-image.sh frontend | cut -c1-12)..."
        echo "backend:  $(./scripts/hash-docker-image.sh backend | cut -c1-12)..."
        echo "nginx:    $(./scripts/hash-docker-image.sh nginx | cut -c1-12)..."
    else
        ./scripts/hash-docker-image.sh {{service}}
    fi
