#!/usr/bin/env bash
# Outputs SHA256 of all files that affect test DB content
# Usage: hash-test-db-sources.sh [--list] [repo-root]  (default root: the checkout holding this script)
#   --list  print the hashed files instead of the hash
#
# Inputs: the populate code, every models file and migration, and each backend
# module the populate code imports directly (it creates or shapes the rows),
# plus events/ledger.py, which events/services.py writes signup history through.
# Not the transitive closure: that is most of the backend, so every PR would
# repopulate. Modules that never change rows (app/cache_utils.py) are left out.
# scripts/slot_tests/test_hash_test_db_sources.py fails when populate gains a
# direct import that is not listed here.
set -euo pipefail

list=false
if [[ "${1:-}" == --list ]]; then
    list=true
    shift
fi

cd "${1:-$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)}"

populate_imports=(
    backend/common/game.py
    backend/discordbot/services/users.py
    backend/events/constants.py
    backend/events/ledger.py
    backend/events/ready_check_constants.py
    backend/events/services.py
    backend/lobby/client.py
    backend/lobby/passwords.py
    backend/lobby/services.py
    backend/lobby/states.py
    backend/org/conduct/constants.py
    backend/org/contributions/kinds.py
    backend/org/contributions/services.py
    backend/org/features.py
    backend/org/leadership/lifecycle.py
    backend/org/leadership/reviews.py
    backend/org/leadership/traits.py
    backend/org/mmr.py
    backend/org/standing/api.py
    backend/steam/functions/stats_update.py
    backend/steam/mocks/mock_match_generator.py
    backend/tests/dota_lobby_sim.py
    backend/tests/helpers/steam_match.py
    backend/tests/test_auth.py
    backend/tournament/choices.py
)

files=$({
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
    \)
    for f in "${populate_imports[@]}"; do
        if [[ -f "$f" ]]; then echo "$f"; fi
    done
} | LC_ALL=C sort -u)

if $list; then
    echo "$files"
else
    echo "$files" | xargs cat | sha256sum | cut -d' ' -f1
fi
