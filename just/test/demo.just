# Test environment demo commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('test::demo')]
all:
    {{inv}} test.demo.all

[group('test::demo')]
create spec="":
    {{inv}} test.demo.create {{ if spec != "" { "--spec " + spec } else { "" } }}

[group('test::demo')]
shuffle:
    {{inv}} test.demo.shuffle

[group('test::demo')]
snake:
    {{inv}} test.demo.snake

[group('test::demo')]
herodraft:
    {{inv}} test.demo.herodraft

[group('test::demo')]
snapshots:
    {{inv}} test.demo.snapshots

[group('test::demo')]
gifs *args:
    {{inv}} test.demo.gifs {{args}}

[group('test::demo')]
trim *args:
    {{inv}} test.demo.trim {{args}}

[group('test::demo')]
quick *args:
    {{inv}} test.demo.quick {{args}}

[group('test::demo')]
clean:
    {{inv}} test.demo.clean
