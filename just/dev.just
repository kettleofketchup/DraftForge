# Development environment commands (dev stack, project df-dev)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
in_env := quote(root / "scripts/in-env.sh")
slots := quote(python) + " -m scripts.slots --root " + quote(root)
compose := in_env + " - . " + slots + " compose --stack dev"

# Migrate the dev DB, then start the dev stack in the foreground (hot reload)
[group('dev')]
debug:
    {{just}} db::migrate::dev
    {{in_env}} dev . {{slots}} compose --stack dev --ansi always up --no-attach nginx --remove-orphans

# Same as debug with the Apple Silicon compose file
[group('dev')]
mac:
    {{just}} db::migrate::dev
    {{in_env}} dev . {{slots}} compose --stack dev-m1 --ansi always up --no-attach nginx --remove-orphans

# Start the dev stack, sync users, tournaments and Steam stats from production, then follow logs (--no-sync: just start it)
[group('dev')]
up *args:
    #!/usr/bin/env bash
    set -euo pipefail
    sync=true
    for arg in "$@"; do
        case "$arg" in
            --no-sync) sync=false ;;
            --sync) sync=true ;;
            *) echo "dev::up: unknown option $arg (use --no-sync)" >&2; exit 2 ;;
        esac
    done
    if [[ "$sync" != true ]]; then
        exec {{compose}} up --remove-orphans
    fi
    {{compose}} up -d --remove-orphans

    echo "Waiting for backend to be ready..."
    ready=false
    deadline=$((SECONDS + ${DF_BACKEND_WAIT_SECS:-120}))
    while (( SECONDS < deadline )); do
        if {{compose}} ps backend --format json 2>/dev/null | grep -qi running \
            && {{compose}} exec -T backend python -c "import requests; requests.get('http://localhost:8000/api/', timeout=5)" >/dev/null 2>&1; then
            ready=true
            break
        fi
        sleep 2
    done
    if [[ "$ready" == true ]]; then
        echo "Backend is ready!"
    else
        echo "Warning: Backend health check timed out, proceeding anyway..."
    fi

    echo
    echo "=== Syncing data from production ==="
    {{just}} dev::sync-all

    echo
    echo "=== Pulling Steam matchmaking stats ==="
    {{just}} db::manage dev populate_steam_matches --relink-users

    echo
    echo "=== Auto-linking tournament games ==="
    echo "Auto-linking tournament games to Steam matches..."
    {{compose}} exec -T backend python -c "$(cat <<'PY'
    import django; django.setup()
    from app.models import Tournament
    from steam.functions.game_linking import auto_link_matches_for_tournament
    results = [auto_link_matches_for_tournament(t.id) for t in Tournament.objects.all()]
    linked = sum(r['auto_linked_count'] for r in results)
    suggestions = sum(r['suggestions_created_count'] for r in results)
    print(f'Auto-linked {linked} games, created {suggestions} suggestions')
    PY
    )" || echo "Warning: auto-link failed; continuing"

    echo
    echo "=== Sync complete, attaching to logs ==="
    exec {{compose}} logs -f

# Start the dev stack detached
[group('dev')]
upd:
    {{compose}} up -d --remove-orphans

[group('dev')]
down:
    {{compose}} down --remove-orphans

[group('dev')]
logs:
    {{compose}} logs -f

[group('dev')]
ps:
    {{compose}} ps

[group('dev')]
restart:
    {{compose}} restart

[group('dev')]
stop:
    {{compose}} stop

[group('dev')]
build:
    {{compose}} build

[group('dev')]
pull:
    {{compose}} pull

[group('dev')]
top:
    {{compose}} top

# Run a shell command in a running dev container: just dev::exec backend 'python manage.py shell'
[group('dev')]
exec service cmd:
    {{compose}} exec "$1" sh -c "$2"

# Run a one-off shell command in a new dev container (default service: backend)
[group('dev')]
run cmd service="backend":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "${1//[[:space:]]/}" ]]; then
        exec {{compose}} run --rm "$2" sh -c "$1"
    fi
    exec {{compose}} run --rm "$2"

# Sync users from production (dota.kettle.sh) into the dev DB (--dry-run to preview)
[group('dev')]
sync-users *flags:
    {{just}} db::migrate::dev
    {{just}} db::manage dev sync_prod_users "$@"

# Sync tournaments from production into the dev DB (--dry-run to preview)
[group('dev')]
sync-tournaments *flags:
    {{just}} db::manage dev sync_prod_tournaments "$@"

# Sync users then tournaments from production (--dry-run to preview)
[group('dev')]
sync-all *flags:
    {{just}} dev::sync-users "$@"
    {{just}} dev::sync-tournaments "$@"

# Start frontend, backend and nginx panes in tmux
[group('dev')]
live:
    cd {{quote(root)}} && ./scripts/tmux.sh

# Migrate the prod DB, then run the production images locally
[group('dev')]
local-prod:
    {{just}} db::migrate::prod
    {{in_env}} prod . {{slots}} compose --stack prod up

# Deploy: migrate, pull the release images, then recreate the release stack
[group('dev')]
release:
    #!/usr/bin/env bash
    set -euo pipefail
    env_file={{quote(root / "backend/.env")}}
    if ! grep -qE '^DJANGO_SECRET_KEY=.+' "$env_file" 2>/dev/null; then
        echo "WARNING: ${env_file} has no DJANGO_SECRET_KEY; Django would sign with the public development key." >&2
        echo "WARNING: generating one and saving it there. Sessions signed with the old key end: everyone logs in again." >&2
        key=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
        printf '\nDJANGO_SECRET_KEY=%s\n' "$key" >> "$env_file"
    fi
    {{just}} db::migrate-env release
    {{just}} docker::release::pull
    version=$(sed -n 's/^VERSION="\(.*\)"$/\1/p' {{quote(root / "docker/.env.release")}} | head -n 1)
    echo "launching release version ${version:-<unset>}"
    {{in_env}} release . {{slots}} compose --stack release down
    {{in_env}} release . {{slots}} compose --stack release up -d

# Launch Chrome with remote debugging for Chrome DevTools MCP
[group('dev')]
chrome url="https://localhost":
    #!/usr/bin/env bash
    set -euo pipefail
    if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
        echo "Chrome debug session already running on :9222"
        echo "Opening $1 in existing session..."
        curl -s "http://127.0.0.1:9222/json/new?$1" > /dev/null 2>&1 || true
        exit 0
    fi
    echo "Starting Chrome with remote debugging on :9222..."
    DISPLAY=:0 google-chrome-stable \
        --remote-debugging-port=9222 \
        --user-data-dir="${HOME}/.chrome-debug" \
        --ignore-certificate-errors \
        --no-first-run \
        --no-default-browser-check \
        "$1" &
    disown
    for _ in $(seq 1 10); do
        if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
            echo "Chrome ready — MCP can connect at http://127.0.0.1:9222"
            exit 0
        fi
        sleep 0.5
    done
    echo "Chrome started but debug port not yet responding (may need a moment)"
