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
# In a git worktree, stops after dependency install (skips dev stack
# startup). There is one dev stack per machine (project df-dev); test stacks
# are per worktree (`just test::slot`). Pass --up to start dev here anyway.
bootstrap *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"

    # Detect worktree once, up front — reused for .env copy + dev-startup skip.
    # In a worktree, .git is a FILE (containing `gitdir: <path>`). In a main
    # checkout, .git is a DIRECTORY. That's the most reliable signal — much
    # more robust than parsing `git rev-parse --git-common-dir`, which
    # returns the relative path `.git` in a main repo and absolute paths in
    # worktrees, so string comparisons against {{root}}/.git or "." misfire.
    is_worktree=false
    main_repo=""
    if [[ -f "{{root}}/.git" ]]; then
        is_worktree=true
        common_dir="$(git rev-parse --git-common-dir 2>/dev/null)"
        # common_dir may be relative or absolute; normalize.
        if [[ "$common_dir" = /* ]]; then
            main_repo="$(dirname "$common_dir")"
        else
            main_repo="$(cd "$common_dir" && pwd | sed 's|/\.git$||')"
        fi
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

    # In a worktree, stop here unless --up was passed: the dev stack (df-dev)
    # is one per machine, while each worktree gets its own test stack slot.
    if [[ "$is_worktree" == "true" && "$force_up" != "true" ]]; then
        echo
        echo "Worktree setup complete — dependencies installed, .env copied."
        echo "  - This worktree gets its own test stack: 'just test::slot' shows its slot and URL."
        echo "  - Run 'just test::setup' / 'just test::upd' to manage that test stack."
        echo "  - The dev stack (df-dev) is one per machine; './dev --up' starts it from here."
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
mod ci 'just/ci.just'
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
mod helm 'just/helm.just'

# Default: show available commands
[private]
default:
    @just --list
