# Docker frontend commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker::frontend')]
build:
    {{inv}} docker.frontend.build

[group('docker::frontend')]
build-prod:
    {{inv}} docker.frontend.build-prod

[group('docker::frontend')]
build-dev:
    {{inv}} docker.frontend.build-dev

[group('docker::frontend')]
push:
    {{inv}} docker.frontend.push
