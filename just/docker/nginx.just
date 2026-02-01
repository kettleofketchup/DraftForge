# Docker nginx commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker::nginx')]
build:
    {{inv}} docker.nginx.build

[group('docker::nginx')]
push:
    {{inv}} docker.nginx.push
