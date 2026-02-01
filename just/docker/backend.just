# Docker backend commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker::backend')]
build:
    {{inv}} docker.backend.build

[group('docker::backend')]
push:
    {{inv}} docker.backend.push
