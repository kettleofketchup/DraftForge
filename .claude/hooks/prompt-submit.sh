#!/usr/bin/env bash
# Remind Claude agents to use just commands

cat << 'EOF'
<system-reminder>
IMPORTANT: This project uses `just` as the command runner.

DO NOT run these directly:
- `inv ...` or `invoke ...` (requires venv activation)
- `npm ...` in frontend/
- `python manage.py ...` in backend/
- `npx playwright ...`

INSTEAD use just recipes:
- `just dev::debug` - start dev environment
- `just test::up` - start test environment
- `just test::pw::headless` - run playwright tests
- `just test::pw::ui` - playwright UI mode
- `just npm::install` - install frontend deps
- `just py::manage <cmd>` - run manage.py commands
- `just db::migrate` - run migrations
- `just db::populate::all` - populate test data

Run `just --list --list-submodules` to see all available commands.
</system-reminder>
EOF
