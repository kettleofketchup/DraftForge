# Demo video recording commands (scripts/demo.py, against this worktree's test slot)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
demo := "cd " + quote(root) + " && " + quote(python) + " -m scripts.demo"

# Record every demo sequentially
[group('demo')]
all:
    {{demo}} all

# Record all demos, or only those matching a spec
[group('demo')]
create spec="":
    {{demo}} create --spec "$1"

[group('demo')]
shuffle:
    {{demo}} shuffle

[group('demo')]
snake:
    {{demo}} snake

[group('demo')]
herodraft:
    {{demo}} herodraft

[group('demo')]
csv:
    {{demo}} csv

[group('demo')]
event-creation:
    {{demo}} event-creation

[group('demo')]
roll-call:
    {{demo}} roll-call

# Site screenshots for the docs
[group('demo')]
snapshots:
    {{demo}} snapshots

# Convert demo videos to GIFs (--duration, --fps, --width, --no-start-from-middle)
[group('demo')]
gifs *args:
    {{demo}} gifs "$@"

# Trim the loading screen from demo videos (--trim-start S, --no-auto)
[group('demo')]
trim *args:
    {{demo}} trim "$@"

# Record, trim, then convert to GIFs (--duration, --fps, --width)
[group('demo')]
quick *args:
    {{demo}} quick "$@"

[group('demo')]
clean:
    {{demo}} clean

# Rewrite git history to drop old demo video/GIF blobs (asks first)
[group('demo')]
git-cleanup:
    {{demo}} git-cleanup
