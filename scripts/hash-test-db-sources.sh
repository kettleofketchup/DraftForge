#!/usr/bin/env bash
# Outputs SHA256 of all files that affect test DB content
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

find backend -type f \( \
    -path "backend/tests/populate.py" -o \
    -path "backend/tests/helpers/tournament_config.py" -o \
    -path "backend/app/management/commands/populate_*.py" -o \
    -path "backend/*/migrations/*.py" -o \
    -name "models.py" \
\) | sort | xargs cat | sha256sum | cut -d' ' -f1
