# Test environment demo commands (same recipes as demo::*)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

[group('test::demo')]
all:
    {{just}} demo::all

[group('test::demo')]
create spec="":
    {{just}} demo::create "$1"

[group('test::demo')]
shuffle:
    {{just}} demo::shuffle

[group('test::demo')]
snake:
    {{just}} demo::snake

[group('test::demo')]
herodraft:
    {{just}} demo::herodraft

[group('test::demo')]
snapshots:
    {{just}} demo::snapshots

[group('test::demo')]
gifs *args:
    {{just}} demo::gifs "$@"

[group('test::demo')]
trim *args:
    {{just}} demo::trim "$@"

[group('test::demo')]
quick *args:
    {{just}} demo::quick "$@"

[group('test::demo')]
clean:
    {{just}} demo::clean
