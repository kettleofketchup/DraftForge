# Docker release commands (production-only images, no -dev)

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker::release')]
build:
    {{inv}} docker.release.build

[group('docker::release')]
push:
    {{inv}} docker.release.push

[group('docker::release')]
pull:
    {{inv}} docker.release.pull
