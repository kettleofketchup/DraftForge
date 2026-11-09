# Documentation commands (MkDocs from the project venv)

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "..")
mkdocs := quote(root / ".venv/bin/mkdocs")

# Start the MkDocs dev server with hot reload
[group('docs')]
serve:
    cd {{quote(root)}} && {{mkdocs}} serve

# Build the static docs site
[group('docs')]
build:
    cd {{quote(root)}} && {{mkdocs}} build
