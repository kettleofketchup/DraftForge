# Development environment commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('dev')]
debug:
    {{inv}} dev.debug

[group('dev')]
upd:
    {{inv}} dev.upd

[group('dev')]
up *args:
    {{inv}} dev.up {{args}}

[group('dev')]
down:
    {{inv}} dev.down

[group('dev')]
logs:
    {{inv}} dev.logs

[group('dev')]
ps:
    {{inv}} dev.ps

[group('dev')]
restart:
    {{inv}} dev.restart

[group('dev')]
stop:
    {{inv}} dev.stop

[group('dev')]
build:
    {{inv}} dev.build

[group('dev')]
pull:
    {{inv}} dev.pull

[group('dev')]
top:
    {{inv}} dev.top

[group('dev')]
exec service cmd:
    {{inv}} dev.exec --service {{service}} --cmd '{{cmd}}'

[group('dev')]
run cmd service="backend":
    {{inv}} dev.run --service {{service}} --cmd '{{cmd}}'

[group('dev')]
sync-users:
    {{inv}} dev.sync-users

[group('dev')]
sync-tournaments:
    {{inv}} dev.sync-tournaments

[group('dev')]
sync-all:
    {{inv}} dev.sync-all

[group('dev')]
live:
    {{inv}} dev.live

[group('dev')]
local-prod:
    {{inv}} dev.prod

[group('dev')]
release:
    {{inv}} dev.release

[group('dev')]
mac:
    {{inv}} dev.mac

# Launch Chrome with remote debugging for Chrome DevTools MCP
[group('dev')]
chrome url="https://localhost":
    #!/usr/bin/env bash
    set -euo pipefail
    if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
        echo "Chrome debug session already running on :9222"
        echo "Opening {{url}} in existing session..."
        # Open URL in existing debug Chrome via CDP
        curl -s "http://127.0.0.1:9222/json/new?{{url}}" > /dev/null 2>&1 || true
        exit 0
    fi
    echo "Starting Chrome with remote debugging on :9222..."
    DISPLAY=:0 google-chrome-stable \
        --remote-debugging-port=9222 \
        --user-data-dir="${HOME}/.chrome-debug" \
        --ignore-certificate-errors \
        --no-first-run \
        --no-default-browser-check \
        "{{url}}" &
    disown
    # Wait for debug port
    for i in $(seq 1 10); do
        if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
            echo "Chrome ready — MCP can connect at http://127.0.0.1:9222"
            exit 0
        fi
        sleep 0.5
    done
    echo "Chrome started but debug port not yet responding (may need a moment)"
