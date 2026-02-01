# Documentation commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('docs')]
serve:
    {{inv}} docs.serve

[group('docs')]
build:
    {{inv}} docs.build
