# Database migration commands (each runs makemigrations, then migrate)

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Migrate dev, prod, then test
[group('db::migrate')]
all:
    {{just}} db::migrate-env dev
    {{just}} db::migrate-env prod
    {{just}} db::migrate-env test

[group('db::migrate')]
dev:
    {{just}} db::migrate-env dev

[group('db::migrate')]
test:
    {{just}} db::migrate-env test

[group('db::migrate')]
prod:
    {{just}} db::migrate-env prod
