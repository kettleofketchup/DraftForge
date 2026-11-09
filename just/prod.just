# Production environment commands (docker-compose.prod.yaml, :latest images).
# Deploys use `just dev::release`.

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
compose := quote(root / "scripts/in-env.sh") + " - . " + quote(python) + " -m scripts.slots --root " + quote(root) + " compose --stack prod"

[group('prod')]
up:
    {{compose}} up --remove-orphans

[group('prod')]
upd:
    {{compose}} up -d --remove-orphans

[group('prod')]
down:
    {{compose}} down --remove-orphans

[group('prod')]
logs:
    {{compose}} logs -f

[group('prod')]
ps:
    {{compose}} ps

[group('prod')]
restart:
    {{compose}} restart

[group('prod')]
stop:
    {{compose}} stop

[group('prod')]
build:
    {{compose}} build

[group('prod')]
pull:
    {{compose}} pull

[group('prod')]
top:
    {{compose}} top

# Run a shell command in a running prod container
[group('prod')]
exec service cmd:
    {{compose}} exec "$1" sh -c "$2"

# Run a one-off shell command in a new prod container (default service: backend)
[group('prod')]
run cmd service="backend":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${1//[[:space:]]/}" ]]; then
        exec {{compose}} run --rm "$2" sh -c "$1"
    fi
    exec {{compose}} run --rm "$2"
