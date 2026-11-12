# Version management commands (scripts/version.py)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
version := "cd " + quote(root) + " && " + quote(python) + " -m scripts.version"

# Release X.Y.Z: assemble changelog.d/, commit, tag, push (--no-commit only rewrites the version files; --no-tag-version skips the tag)
[group('version')]
set ver *flags:
    {{version}} set "$@"

# Write a version (--version X.Y.Z, default: docker/.env.release's) everywhere, then build the release images
[group('version')]
build *args:
    {{version}} sync "$@"
    {{just}} docker::release::build

# Copy docker/.env.release's VERSION to pyproject.toml (--env-file F for another)
[group('version')]
from-env *args:
    {{version}} from-env "$@"

# Copy pyproject.toml's version to docker/.env.prod and docker/.env.release
[group('version')]
from-pyproject:
    {{version}} from-pyproject
