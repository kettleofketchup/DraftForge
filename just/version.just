# Version management commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('version')]
set ver:
    {{inv}} version.set {{ver}}

[group('version')]
build:
    {{inv}} version.build

[group('version')]
from-env:
    {{inv}} version.from-env

[group('version')]
from-pyproject:
    {{inv}} version.from-pyproject
