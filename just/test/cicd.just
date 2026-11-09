# CI/CD test commands

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Backend tests, then Playwright with a full setup
[group('test::cicd')]
all:
    {{just}} test::cicd::backend
    {{just}} test::cicd::playwright

# test::setup, then every Playwright test
[group('test::cicd')]
playwright:
    {{just}} test::setup
    {{just}} test::pw::all

[group('test::cicd')]
backend:
    {{just}} test::backend::all
