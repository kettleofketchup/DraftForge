# Frontend validation and tooling.
#
# `validate` is a local-developer convenience. In CI, each recipe runs as a
# separate parallel job so failures don't mask each other. See follow-up Task
# 22 for the CI YAML wiring.

frontend := source_directory() / ".." / ".." / "frontend"

mod i18n 'i18n.just'

# Type-check the frontend
[group('frontend')]
tsc:
    cd "{{frontend}}" && npm run typecheck

# Lint the frontend (navbar-scoped during initial rollout)
[group('frontend')]
lint:
    cd "{{frontend}}" && npm run lint

# Design-system lint (@shadcn/lint) over app/, against the suppressions baseline
[group('frontend')]
lint-shadcn:
    cd "{{frontend}}" && npm run lint:shadcn

# Drop baseline entries for shadcn-lint violations that have been fixed
[group('frontend')]
lint-shadcn-prune:
    cd "{{frontend}}" && npm run lint:shadcn:prune

# Run all frontend validators (LOCAL convenience; CI parallelizes)
[group('frontend')]
validate: tsc lint lint-shadcn
    just frontend::i18n::check
    just frontend::i18n::guard
