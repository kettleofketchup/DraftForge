# Just Commands

This project uses [just](https://github.com/casey/just) as its only task runner. Recipes call
the project venv's Python (`.venv/bin/python`) directly, so no `source .venv/bin/activate` is
needed. `./dev` installs just and creates the venv in a fresh clone.

!!! info "Listing All Commands"
    ```bash
    just --list --list-submodules
    ```

## Command Namespaces

| Namespace | Description |
|-----------|-------------|
| `dev::*` | Development environment (dev stack, project `df-dev`) |
| `docker::*` | Image builds, pushes and pulls |
| `db::*` | Migrations and test data population |
| `test::*` | Test stack, Playwright, backend tests |
| `update::*` | Dependency updates |
| `version::*` | Version management and releases |
| `ci::*` | CI entry points (`ci::changelog-check`, `ci::shellcheck`) |
| `prod::*` | Production compose stack (`:latest` images) |
| `demo::*` | Demo video recording |
| `docs::*` | Documentation commands |
| `discord::*` | Discord bot helpers |
| `helm::*` | Helm chart for preview environments |
| `py::*` | Python/Django commands |

## Development Commands (`just dev::*`)

```bash
just dev::debug              # Migrate dev, then start the dev stack in the foreground (hot reload)
just dev::mac                # Same with the Apple Silicon compose file
just dev::up                 # Start detached, sync users/tournaments/Steam stats from prod, follow logs
just dev::up --no-sync       # Just start the dev stack in the foreground
just dev::upd                # Start the dev stack detached
just dev::down               # Stop and remove the dev stack
just dev::logs | ps | restart | stop | build | pull | top
just dev::exec <svc> '<cmd>' # Shell command in a running dev container
just dev::run '<cmd>' [svc]  # One-off shell command in a new container (default: backend)
just dev::sync-all [--dry-run]   # sync-users then sync-tournaments from production
just dev::live               # tmux panes for frontend, backend and nginx
just dev::local-prod         # Migrate prod, then run the production images locally
just dev::release            # Deploy: migrate, pull release images, recreate the release stack
```

## Docker Commands (`just docker::*`)

Builds use `docker buildx` with a registry cache. Every image is tagged `:latest` and
`:<content-hash>` (`scripts/hash-docker-image.sh`); `--release` adds `:<version>` from
`pyproject.toml`. Without `--push` the image is loaded locally.

### Build
```bash
just docker::all-build [--push]   # backend, frontend and nginx in parallel
just docker::backend::build       # backend and backend-dev
just docker::frontend::build      # frontend and frontend-dev
just docker::frontend::build-dev  # frontend-dev only (Playwright image)
just docker::nginx::build
just docker::release::build       # version-tagged release images
```

### Push
```bash
just docker::all-push
just docker::backend::push | frontend::push | nginx::push
just docker::release::push
```

### Pull
```bash
just docker::all-pull         # By content hash, else :latest; fails if any image is missing
just docker::release::pull    # Production images only; a missing image only warns
```

### Test Database
```bash
just docker::db::hash         # Output content hash for test-db sources
just docker::db::build        # Build test-db image (skips if hash unchanged)
just docker::db::pull         # Pull from GHCR (tries hash first, then latest)
just docker::db::push         # Push to GHCR (both hash and latest tags)
```

## Database Commands (`just db::*`)

These run `manage.py` on the host with `docker/.env.<env>` loaded and `DISABLE_CACHE=true`.

```bash
# Migrations (each runs makemigrations for the project apps, then migrate)
just db::migrate::dev | test | prod
just db::migrate::all         # dev, prod, then test
just db::run-migrate          # Same as db::migrate::dev
just db::makemigrations [app...]  # Default: every app in `apps` (just/db/mod.just)

# Population (test env; add --force to repopulate)
just db::populate::all        # Build or reuse the cached test-db image, then extract it
just db::populate::fresh      # New test DB, migrate, populate_all --force
just db::populate::users | organizations | tournaments | test-auth-users | steam | steam-mock
just db::populate::test-tournaments | bracket-linking | bracket-unset-winner | real-tournament
just db::populate::demo-tournaments | csv-import | user-edit | shuffle-tie
just db::reset-test           # Extract cached DB to backend/test.db.sqlite3
```

`makemigrations` takes the explicit app list in `just/db/mod.just`; it does not read
`INSTALLED_APPS`. Add a new Django app there too.

## Test Commands (`just test::*`)

### Playwright

Every Playwright recipe goes through `just test::pw::run`, which exports this worktree's
slot URL (`DF_BASE_URL`), flushes the test Redis, then runs `npx playwright test` in `frontend/`.

```bash
just test::pw::run <args>       # npx playwright test <args> against this slot
just test::pw::headless [args]  # chromium, herodraft and events-sequential projects
just test::pw::ui | debug | report | install
just test::pw::spec <pattern>   # Spec files whose path matches, --no-deps
just test::pw::grep '<title>'   # Tests whose title matches, --no-deps
just test::pw::navigation | tournament | draft | bracket | league | herodraft | all
just test::pw::cicd             # @cicd tests across every project
just test::pw::cicd-chromium --shard=1/4   # CI shard runners (also cicd-mobile, cicd-herodraft, cicd-events)
```

### Environment Management

```bash
just test::setup              # Stop, update deps, build images, fresh populate, start detached
just test::up | upd           # Start this worktree's test stack (foreground | detached)
just test::down               # Stop this worktree's test stack (scoped to its slot)
just test::logs | ps | restart | stop | build | pull | top
just test::exec <svc> '<cmd>'
```

### Test Stack Slots

Each worktree runs its own test stack in a slot. See
[Test Stack Slots](test-stack-slots.md).

```bash
just test::slot                    # Allocate or re-adopt this worktree's slot; print slot, project, URL
just test::slots                   # List every slot reservation and df* stack (read-only, never allocates)
just test::slot-release            # Release this worktree's slot (stack must be down)
just test::slot-release --slot N   # Release another worktree's idle slot N (ask the user first)
just test::slot-claim N            # Move slot N to this worktree (ask the user first)
just test::slot-reap <project>     # Tear down an orphaned df/df-sN/df-dev/df-run-* stack (ask the user first)
just test::background on|off       # Discord bot + celery beat for this slot (off by default on N >= 1)
just test::compose <args>          # docker compose against this worktree's slot (--stack dev for df-dev)
just test::slots-unit              # Slot helper and just recipe tests (no containers)
```

### Backend Tests

```bash
just test::run '<command>'    # One-off command in a test container, image entrypoint bypassed
just test::backend::all       # pytest on the host with the test env loaded (also ::steam, ::draft)
```

## Update Commands (`just update::*`)

```bash
just update::all       # git pull, migrate dev, then (online) npm install, poetry install, image pulls
just update::all-test  # (online) npm install and poetry install
just update::git | npm | python
```

## Version Commands (`just version::*`)

```bash
just version::set 1.2.3               # Release: assemble changelog, commit, tag, push (see changelog.md)
just version::set 1.2.3 --no-commit   # Only rewrite the version files (+ local tag unless --no-tag-version)
just version::build [--version X.Y.Z] # Write the version everywhere, then build the release images
just version::from-env                # docker/.env.release VERSION -> pyproject.toml
just version::from-pyproject          # pyproject.toml version -> docker/.env.prod and .env.release
```

## Production Commands (`just prod::*`)

`docker-compose.prod.yaml` with the `:latest` images. Deploys use `just dev::release`.

```bash
just prod::up | upd | down | logs | ps | restart | stop | build | pull | top
just prod::exec <svc> '<cmd>'
just prod::run '<cmd>' [svc]
```

## Python/Django Commands (`just py::*`)

```bash
just py::manage <command>    # Django management commands
just py::shell               # Django shell (with cache disabled)
just py::runserver           # Run server directly
just py::test                # pytest on the host with docker/.env.test loaded
just py::migrate             # Run migrations (cache disabled)
```

## Demo Commands (`just demo::*`)

Record demo videos of features using Playwright against this worktree's test slot, then
convert them to GIFs for documentation (`scripts/demo.py`; `just test::demo::*` are aliases).

```bash
just demo::all                         # Record every demo
just demo::create [spec]               # All demos, or those matching spec
just demo::shuffle | snake | herodraft | csv | event-creation | roll-call
just demo::snapshots                   # Site screenshots
just demo::trim [--trim-start S] [--no-auto]
just demo::gifs [--duration 10] [--fps 12] [--width 400] [--no-start-from-middle]
just demo::quick                       # create, trim, then gifs
just demo::clean
```

Output locations:

- Videos: `https://assets.kettle.sh/draftforge/videos/`
- GIFs: `https://assets.kettle.sh/draftforge/gifs/`

## Docs Commands (`just docs::*`)

```bash
just docs::serve      # Start MkDocs dev server
just docs::build      # Build static documentation site
```

## Discord Commands (`just discord::*`)

```bash
just discord::ngrok [port]    # ngrok tunnel for Discord interactions (default 443)
just discord::logs [stack]    # Follow the bot's logs (dev, default, or test)
```

## Helm Commands (`just helm::*`)

The chart in `helm/` deploys per-PR preview environments. See `helm/README.md`.

```bash
just helm::plugins            # Install the pinned helm-unittest plugin
just helm::lint               # Lint the default and preview profiles
just helm::template preview   # Render a profile (default or preview)
just helm::test               # Unit tests, budget, render-safety, kubeconform, script tests
```

## How the Recipes Are Built

- The root `justfile` declares one module per namespace; module files live in `just/`.
- Modules run recipes with `bash -euo pipefail` and `set positional-arguments`, so
  arguments reach commands as `"$1"`/`"$@"` with their quoting intact.
- Every compose call goes through the slot helper, `python -m scripts.slots compose`
  (exposed as `just test::compose`); recipes never run `docker compose` directly.
- `scripts/in-env.sh <env> <dir> <cmd>` loads `docker/.env.<env>` before a command.
  Values in the env file override variables already set in your shell.
- Logic that needs Python lives in small CLIs: `scripts/demo.py`, `scripts/version.py`,
  `scripts/compose.py` (Playwright base URL, Redis flush) and `scripts/slots.py`.
- `DF_JUST_PYTHON` overrides the venv Python; the recipe tests in
  `scripts/slot_tests/test_just_recipes.py` use it to record what each recipe runs.

### Shellcheck

`just ci::shellcheck` renders every recipe with `just --dry-run` and runs
[ShellCheck](https://www.shellcheck.net/) on it with the shell it runs under. The
`shellcheck` CI job runs it on every pull request. Check one recipe while editing:

```bash
just ci::shellcheck test::pw::run
```

Silence a finding only with a `# shellcheck disable=SCxxxx` comment on the line before,
and say why.
