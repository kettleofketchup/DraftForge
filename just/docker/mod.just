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
