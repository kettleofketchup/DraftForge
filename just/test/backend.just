# Backend test commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('test::backend')]
all:
    {{inv}} test.backend.all

[group('test::backend')]
steam:
    {{inv}} test.backend.steam

[group('test::backend')]
draft:
    {{inv}} test.backend.draft
