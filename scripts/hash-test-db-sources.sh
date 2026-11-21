#!/usr/bin/env bash
# Outputs SHA256 of all files that affect test DB content
# Usage: hash-test-db-sources.sh [repo-root]  (default: the checkout holding this script)
set -euo pipefail

cd "${1:-$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)}"

find backend -type f \( \
    -path "backend/tests/populate.py" -o \
    -path "backend/tests/populate/*.py" -o \
    -path "backend/tests/data/*.py" -o \
    -path "backend/tests/helpers/tournament_config.py" -o \
    -path "backend/app/management/commands/populate_*.py" -o \
    -path "backend/*/migrations/*.py" -o \
    -path "backend/*/models/*.py" -o \
    -path "backend/*/models_*.py" -o \
    -name "models.py" \
\) | LC_ALL=C sort | xargs cat | sha256sum | cut -d' ' -f1
