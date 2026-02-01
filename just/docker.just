# Docker build and push commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docker')]
all-build:
    {{inv}} docker.all.build

[group('docker')]
all-push:
    {{inv}} docker.all.push

[group('docker')]
all-pull:
    {{inv}} docker.all.pull

[group('docker')]
backend-build:
    {{inv}} docker.backend.build

[group('docker')]
backend-push:
    {{inv}} docker.backend.push

[group('docker')]
frontend-build:
    {{inv}} docker.frontend.build

[group('docker')]
frontend-build-prod:
    {{inv}} docker.frontend.build-prod

[group('docker')]
frontend-build-dev:
    {{inv}} docker.frontend.build-dev

[group('docker')]
frontend-push:
    {{inv}} docker.frontend.push

[group('docker')]
nginx-build:
    {{inv}} docker.nginx.build

[group('docker')]
nginx-push:
    {{inv}} docker.nginx.push
