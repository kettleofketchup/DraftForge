# Database commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

mod migrate 'migrate.just'
mod populate 'populate.just'

[group('db')]
run-migrate:
    {{inv}} db.migrate

[group('db')]
makemigrations *args:
    {{inv}} db.makemigrations {{args}}
