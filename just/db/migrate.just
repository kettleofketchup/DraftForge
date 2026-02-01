# Database migration commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('db::migrate')]
all:
    {{inv}} db.migrate.all

[group('db::migrate')]
dev:
    {{inv}} db.migrate.dev

[group('db::migrate')]
test:
    {{inv}} db.migrate.test

[group('db::migrate')]
prod:
    {{inv}} db.migrate.prod
