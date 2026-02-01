# CI/CD test commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('test::cicd')]
all:
    {{inv}} test.cicd.all

[group('test::cicd')]
playwright:
    {{inv}} test.cicd.playwright

[group('test::cicd')]
backend:
    {{inv}} test.cicd.backend
