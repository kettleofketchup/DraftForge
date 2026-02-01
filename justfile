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
    inv dev.debug {{args}}

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

# Default: show available commands
[private]
default:
    @just --list
