# Update commands (git, deps, images)

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('update')]
all:
    {{inv}} update.all

[group('update')]
all-test:
    {{inv}} update.all-test

[group('update')]
git:
    {{inv}} update.git

[group('update')]
npm:
    {{inv}} update.npm

[group('update')]
python:
    {{inv}} update.python
