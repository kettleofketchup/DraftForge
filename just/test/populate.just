# Test database population commands
# These commands run against the TEST environment

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

# Populate all test data (resets test database)
[group('test::populate')]
all:
    {{inv}} db.populate.all

# Populate organizations and leagues
[group('test::populate')]
organizations:
    {{inv}} db.populate.organizations

# Populate users
[group('test::populate')]
users:
    {{inv}} db.populate.users

# Populate test auth users (for Playwright/Cypress E2E tests)
[group('test::populate')]
test-auth-users:
    {{inv}} db.populate.test-auth-users

# Populate tournaments
[group('test::populate')]
tournaments:
    {{inv}} db.populate.tournaments

# Populate test scenario tournaments (for E2E tests)
[group('test::populate')]
test-tournaments:
    {{inv}} db.populate.test-tournaments

# Populate demo tournaments
[group('test::populate')]
demo-tournaments:
    {{inv}} db.populate.demo-tournaments

# Populate bracket linking scenarios
[group('test::populate')]
bracket-linking:
    {{inv}} db.populate.bracket-linking

# Populate real tournament data
[group('test::populate')]
real-tournament:
    {{inv}} db.populate.real-tournament

# Populate mock Steam data
[group('test::populate')]
steam-mock:
    {{inv}} db.populate.steam-mock
