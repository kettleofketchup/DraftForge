# Test database population commands (aliases of db::populate::*, test env)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Reset the test database and populate everything (db::populate::fresh)
[group('test::populate')]
all:
    {{just}} db::populate::fresh

# Populate organizations and leagues
[group('test::populate')]
organizations *flags:
    {{just}} db::populate::organizations "$@"

[group('test::populate')]
users *flags:
    {{just}} db::populate::users "$@"

# Populate test auth users (for Playwright E2E tests)
[group('test::populate')]
test-auth-users *flags:
    {{just}} db::populate::test-auth-users "$@"

[group('test::populate')]
tournaments *flags:
    {{just}} db::populate::tournaments "$@"

# Populate test scenario tournaments (for E2E tests)
[group('test::populate')]
test-tournaments *flags:
    {{just}} db::populate::test-tournaments "$@"

[group('test::populate')]
demo-tournaments *flags:
    {{just}} db::populate::demo-tournaments "$@"

[group('test::populate')]
bracket-linking *flags:
    {{just}} db::populate::bracket-linking "$@"

[group('test::populate')]
real-tournament *flags:
    {{just}} db::populate::real-tournament "$@"

[group('test::populate')]
steam-mock *flags:
    {{just}} db::populate::steam-mock "$@"
