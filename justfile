# DraftForge Command Runner
# Usage: just --list

set quiet
set dotenv-load
set shell := ["bash", "-c"]

root := justfile_directory()
venv := root / ".venv/bin/activate"
frontend := root / "frontend"

# Bootstrap and start dev environment (for ./dev script)
# Called by: ./dev
bootstrap *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"
    if [[ ! -d "{{root}}/.venv" ]]; then
        echo "Creating Python virtual environment..."
        python3 -m venv "{{root}}/.venv"
        source "{{venv}}"
        pip install -q poetry
        poetry install -q
    else
        source "{{venv}}"
    fi
    if [[ ! -d "{{frontend}}/node_modules" ]]; then
        echo "Installing frontend dependencies..."
        cd "{{frontend}}" && npm install
        cd "{{root}}"
    fi
    # If running in a git worktree, copy backend/.env from the main repo
    main_repo="$(git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
    if [[ -n "$main_repo" && "$main_repo" != "{{root}}/.git" && "$main_repo" != "." ]]; then
        if [[ -f "$main_repo/backend/.env" && ! -f "{{root}}/backend/.env" ]]; then
            echo "Worktree detected — copying backend/.env from main repo..."
            cp "$main_repo/backend/.env" "{{root}}/backend/.env"
        fi
    fi
    # Use M1 compose on macOS ARM, standard compose elsewhere
    if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
        echo "Detected macOS ARM — using M1 Docker Compose config"
        inv dev.mac {{args}}
    else
        inv dev.debug {{args}}
    fi

# Modules (namespaced with ::)
mod dev 'just/dev.just'
mod docker 'just/docker/mod.just'
mod demo 'just/demo.just'
mod docs 'just/docs.just'
mod frontend 'just/frontend/mod.just'
mod update 'just/update.just'
mod version 'just/version.just'
mod prod 'just/prod.just'
mod discord 'just/discord.just'
mod npm 'just/npm.just'
mod py 'just/py.just'
mod test 'just/test/mod.just'
mod db 'just/db/mod.just'
mod r2 'just/r2.just'

# Default: show available commands
[private]
default:
    @just --list
