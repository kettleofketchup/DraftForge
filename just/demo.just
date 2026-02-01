# Demo video recording commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('demo')]
all:
    {{inv}} demo.all

[group('demo')]
create spec="":
    {{inv}} demo.create {{ if spec != "" { "--spec " + spec } else { "" } }}

[group('demo')]
shuffle:
    {{inv}} demo.shuffle

[group('demo')]
snake:
    {{inv}} demo.snake

[group('demo')]
herodraft:
    {{inv}} demo.herodraft

[group('demo')]
snapshots:
    {{inv}} demo.snapshots

[group('demo')]
gifs *args:
    {{inv}} demo.gifs {{args}}

[group('demo')]
trim *args:
    {{inv}} demo.trim {{args}}

[group('demo')]
quick *args:
    {{inv}} demo.quick {{args}}

[group('demo')]
clean:
    {{inv}} demo.clean
