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
#
# In a git worktree, stops after dependency install (skips docker compose
# startup) — worktrees share the main repo's docker stack and shouldn't
# spin up a parallel one. Pass --up to force docker startup anyway.
bootstrap *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"

    # Detect worktree once, up front — reused for .env copy + dev-startup skip.
    main_repo="$(git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
    is_worktree=false
    if [[ -n "$main_repo" && "$main_repo" != "{{root}}/.git" && "$main_repo" != "." ]]; then
        is_worktree=true
    fi

    # Parse --up out of args (forces docker startup even in worktree).
    force_up=false
    passthrough_args=()
    for arg in {{args}}; do
        case "$arg" in
            --up) force_up=true ;;
            *) passthrough_args+=("$arg") ;;
        esac
    done

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
    if [[ "$is_worktree" == "true" ]]; then
        if [[ -f "$main_repo/backend/.env" && ! -f "{{root}}/backend/.env" ]]; then
            echo "Worktree detected — copying backend/.env from main repo..."
            cp "$main_repo/backend/.env" "{{root}}/backend/.env"
        fi
    fi

    # In a worktree, stop here unless --up was passed. Worktrees share the
    # main repo's docker stack (project name pinned by an earlier fix) and
    # spinning up a parallel one collides.
    if [[ "$is_worktree" == "true" && "$force_up" != "true" ]]; then
        echo
        echo "Worktree setup complete — dependencies installed, .env copied."
        echo "  - Run 'just dev::debug' from the main repo to start docker compose."
        echo "  - Run 'just test::setup' / 'just test::upd' to manage the test stack."
        echo "  - Re-run './dev --up' here to force docker startup in this worktree."
        exit 0
    fi

    # Use M1 compose on macOS ARM, standard compose elsewhere
    if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
        echo "Detected macOS ARM — using M1 Docker Compose config"
        inv dev.mac "${passthrough_args[@]}"
    else
        inv dev.debug "${passthrough_args[@]}"
    fi

# Modules (namespaced with ::)
mod dev 'just/dev.just'
mod docker 'just/docker/mod.just'
mod demo 'just/demo.just'
mod docs 'just/docs.just'
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
