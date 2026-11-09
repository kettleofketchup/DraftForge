# Database population commands (test env). Each takes --force to repopulate.

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Smart populate: builds cached image if needed, then extracts
[group('db::populate')]
all:
    {{just}} docker::db::build
    {{just}} db::reset-test

# Force fresh populate (bypasses cache): new test DB, migrate, populate_all --force
[group('db::populate')]
fresh:
    rm -f {{quote(root / "backend/test.db.sqlite3")}}
    touch {{quote(root / "backend/test.db.sqlite3")}}
    {{just}} db::migrate::test
    {{just}} db::manage test populate_all --force

[group('db::populate')]
users *flags:
    {{just}} db::migrate::test
    {{just}} db::manage test populate_users "$@"

[group('db::populate')]
organizations *flags:
    {{just}} db::migrate::test
    {{just}} db::populate::call tests.populate populate_organizations_and_leagues "$@"

[group('db::populate')]
tournaments *flags:
    {{just}} db::manage test populate_tournaments "$@"

# Test authentication users for Playwright
[group('db::populate')]
test-auth-users *flags:
    {{just}} db::manage test populate_test_auth_users "$@"

# Real Steam match data from the Steam API (--full-sync for everything)
[group('db::populate')]
steam *flags:
    {{just}} db::manage test populate_steam_matches --relink-users "$@"

[group('db::populate')]
steam-mock *flags:
    {{just}} db::populate::call tests.populate populate_steam_matches "$@"

# Test scenario tournaments for E2E tests
[group('db::populate')]
test-tournaments *flags:
    {{just}} db::populate::call tests.helpers.tournament_config populate_test_tournaments "$@"

[group('db::populate')]
bracket-linking *flags:
    {{just}} db::populate::call tests.populate populate_bracket_linking_scenario "$@"

[group('db::populate')]
bracket-unset-winner *flags:
    {{just}} db::populate::call tests.populate populate_bracket_unset_winner_tournament "$@"

# Real tournament 38 data
[group('db::populate')]
real-tournament *flags:
    {{just}} db::populate::call tests.populate populate_real_tournament_38 "$@"

# Demo tournaments for video recording
[group('db::populate')]
demo-tournaments *flags:
    {{just}} db::populate::call tests.populate populate_demo_tournaments "$@"

[group('db::populate')]
csv-import *flags:
    {{just}} db::populate::call tests.populate populate_csv_import_data "$@"

[group('db::populate')]
user-edit *flags:
    {{just}} db::populate::call tests.populate populate_user_edit_data "$@"

[group('db::populate')]
shuffle-tie *flags:
    {{just}} db::populate::call tests.populate populate_shuffle_tie_data "$@"

# Call module.func(force=...) through manage.py shell
[private]
call module func *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    force=False
    for flag in "${@:3}"; do
        case "$flag" in
            --force) force=True ;;
            *) echo "db::populate: unknown option $flag (only --force)" >&2; exit 2 ;;
        esac
    done
    exec {{just}} db::manage test shell -c "from $1 import $2; $2(force=$force)"
