# Database population commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('db::populate')]
all:
    {{inv}} db.populate.all

[group('db::populate')]
users:
    {{inv}} db.populate.users

[group('db::populate')]
tournaments:
    {{inv}} db.populate.tournaments

[group('db::populate')]
organizations:
    {{inv}} db.populate.organizations

[group('db::populate')]
demo-tournaments:
    {{inv}} db.populate.demo-tournaments

[group('db::populate')]
test-tournaments:
    {{inv}} db.populate.test-tournaments

[group('db::populate')]
bracket-linking:
    {{inv}} db.populate.bracket-linking

[group('db::populate')]
real-tournament:
    {{inv}} db.populate.real-tournament

[group('db::populate')]
steam:
    {{inv}} db.populate.steam

[group('db::populate')]
steam-mock:
    {{inv}} db.populate.steam-mock
