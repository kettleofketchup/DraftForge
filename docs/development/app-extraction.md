# Backend App Extraction

`backend/app` started as the only Django app and still holds most of the backend. We are splitting it into domain apps one slice per PR, models included. Each PR moves one slice, and `app/` only ever gets smaller.

The first slice moved the hero draft family into the new `draft` app. This page is the recipe that slice followed, written so later slices can repeat it step by step.

Planned slices, in order:

| Slice | Source app | Target app |
|-------|-----------|------------|
| Hero draft (done) | `app` | `draft` |
| Team draft (`Draft`, `DraftRound`, `DraftEvent`, `DraftOptions`, teamdraft/shuffle/draft_picks, `draft_tick`, `teamdraft_tick`) | `app` | `draft` |
| Leagues, ratings, matches | `app` | per domain |
| Org and league logs | `app` | per domain |
| Bracket and tournament | `bracket` | `tournament` |

`CustomUser` stays in `app` (it is `AUTH_USER_MODEL`).

## Rules for every slice

- No DDL. Models move with state-only migrations (`SeparateDatabaseAndState`) and keep their table names through `Meta.db_table`.
- No behaviour change. Public HTTP and WebSocket paths, URL `name=`s, Redis keys, channel groups, message `type`s and log `system=`/`subsystem=` values stay the same.
- No re-export shims in the source app. Every importer is rewritten to the new location.
- The guard in `backend/tests/test_app_boundaries.py` gets one new `MovedSlice` entry per slice.
- Inside the target app, keep each draft kind (or other sub-domain) in its own module: `models/hero.py`, `services/hero.py`, `tasks/hero_tick.py`, `consumers/hero.py`, `views/hero.py`, and so on.

## Worktree setup

Do the work in a worktree. Two things trip people up there.

**Every `just` call needs the `cd` prefix.** A bare `just ...` resolves the justfile from the shell's working directory. If that is the main checkout, the recipe runs main's code against main's test slot and reports green. Agent shells reset their cwd between calls, so write every call like this:

```bash
cd /path/to/.worktrees/<slice> && just test::run 'python manage.py test draft -v 2' # allow-cd
```

The `# allow-cd` suffix is what lets the hook accept a compound `cd ... &&`. For git, use `git -C <worktree> ...`.

**Link the main venv.** A fresh worktree has no `.venv`, and `just docs::build` hardcodes `.venv/bin/mkdocs`. Link the main checkout's venv (it is gitignored):

```bash
ln -s /path/to/draftforge/.venv /path/to/.worktrees/<slice>/.venv
```

Do not run `poetry lock`, `uv run` or `uv run mkdocs` in the worktree. Each of them can create or resync a venv and wipe the shared one.

If containers fail with `EACCES` or "readonly database" under rootless podman:

```bash
setfacl -R -m u:100999:rwX -m d:u:100999:rwX <worktree>/backend <worktree>/frontend
```

## The recipe

### 1. Inventory the slice

List the models, modules, string references and inbound importers. String references are the ones that get missed: lazy FK strings, signal senders, `mock.patch` targets, cacheops keys and anything built from `_meta.label`.

```bash
B=<worktree>/backend
# Python importers, absolute and relative
grep -rnE "from app\.models import|from \.models import|import app\.models" $B --include='*.py' | grep -E "HeroDraft|DraftTeam"
# Lazy model strings (FKs, senders, apps.get_model)
grep -rnE "['\"]app\.(HeroDraft|DraftTeam|herodraft|draftteam)" $B --include='*.py'
# Patch targets, single and multi-line
grep -rn "app.functions.herodraft" $B --include='*.py'
rg -U "patch\(\s*\n\s*['\"]app\.functions\.herodraft" $B -g '*.py'
# Cacheops keys
grep -n "\"app\." $B/backend/settings.py
# _meta.label users
grep -rn "_meta.label" $B --include='*.py'
```

Swap in the slice's own model and module names. The relative form (`from .models import`) matters: the hero slice missed one in `app/views_main.py` on the first pass.

### 2. Create or extend the target app

For a new app:

- Add `backend/<new_app>/` with `apps.py`, and empty `models/__init__.py`, `migrations/__init__.py`, `tests/__init__.py`.
- Add it to `MODEL_APPS` in `backend/config/installed_apps.py`. Celery installs only `MODEL_APPS`.
- Add it to the `apps` list in `just/db/mod.just` **and** to `APPS` in `scripts/slot_tests/test_just_recipes.py`. `scripts/slot_tests/test_app_lists.py` fails if any `MODEL_APPS` entry with migrations is missing from either list.
- Add `backend/<new_app>/**` to the matching label in `.github/labeler.yml`.

Not every source app is `app`:

- `bracket` is its own app (label `bracket`, `bracket.apps.TournamentConfig`, tables `bracket_*`). The bracket/tournament slice uses `source_app="bracket"`, and its tables keep the `bracket_` prefix.
- `backend/tournament/` holds only a stray 0-byte `models.py` and no `__init__.py`. The tournament slice must create the app properly or delete that file first.

### 3. Land prep commits first

Behaviour-neutral prep goes in separate commits before anything moves: decoupling edges from shared code into the slice, deleting dead code, adding `dispatch_uid` to receivers that will move, and infra list fixes. That keeps the move commits mechanical and easy to review.

### 4. Move the model code

Copy the classes into `<new_app>/models/<kind>.py` unchanged and add `Meta.db_table = "<source_app>_<model_label>"`. Keep existing `ordering` and other `Meta` options. Re-export the names from `<new_app>/models/__init__.py` with `__all__`.

### 5. Write the state-only migrations

Generate them with `cd <worktree> && just db::makemigrations <new_app> <other apps with FKs> <source_app> # allow-cd`, then wrap each operation list in `SeparateDatabaseAndState(state_operations=[...], database_operations=[])`. Files generated inside the container are owned by uid 100999. Write the final migrations yourself and delete the generated ones.

The order is:

1. `<new_app>/0001`: `CreateModel` for each model. It depends on the source app's current leaf.
2. One migration per app with FKs to the moved models, holding state-only `AlterField`s. A real `AlterField` on SQLite rebuilds the referencing table for nothing.
3. `<source_app>/<next>`: `RemoveField` for fields that close a cycle, then `DeleteModel`, then a `RunPython` that relabels the `django_content_type` rows from `<source_app>` to `<new_app>`. It depends on the other two and on `("contenttypes", "0002_remove_content_type_name")`.

The ContentType relabel is required. Without it, `post_migrate` creates new permission rows that nobody holds, and the existing user and group grants stay behind on stale rows. The relabel must be symmetric and defensive: for each model, skip it (and log once) when the destination row already exists, in both directions. Then neither direction can hit `UNIQUE(app_label, model)`. See `backend/app/migrations/0107_move_hero_draft_models_to_draft.py`.

Check that no SQL runs and nothing is left over:

```bash
cd <worktree> && just test::run 'python manage.py sqlmigrate draft 0001 && python manage.py makemigrations --check --dry-run' # allow-cd
```

Add a committed reversal test that drives `MigrationExecutor` backwards and forwards (`backend/draft/tests/test_hero_move_migration.py`). `django-test-migrations`' `MigratorTestCase` only migrates forward, so it does not cover reversal. Include the duplicate-ContentType case.

### 6. Commit order: code first, models last

Every commit must pass `manage.py check`, the tests that touch the slice and both CI groups. The hero slice used this order:

1. **Prep commits** (step 3).
2. **Empty app** registered in `MODEL_APPS`, the `just` app lists and the labeler.
3. **Non-model code moves** while the models stay in the source app: services, tasks, serializers, then consumers, views, routes, admin, signals and internal endpoints. The moved code imports the models from `<source_app>.models`, so each commit still passes `manage.py check`. Use `git mv` so history follows, and hoist function-local imports to module top as you go.
4. **Model move**: model classes, the three migrations, cacheops keys, lazy FK strings and signal senders, plus every model importer rewritten in one commit. A models-only commit cannot pass `check`, because moving the classes breaks every old importer at once.
5. **Test move**: `git mv` slice-only test modules into `<new_app>/tests/` as `test_<kind>_*.py`. Leave mixed test files where they are until a later slice empties them.
6. **Guard entry** (step 9).
7. **Docs and changelog** (steps 10 and 11).

After each commit, run the touched-name sweep (every test module that mentions the slice):

```bash
grep -rlE 'HeroDraft|DraftTeam|herodraft|HERODRAFT' <worktree>/backend --include='test*.py'
```

Convert the paths to dotted labels and pass them to `just test::run`. For commits that move code, also run both CI groups:

```bash
cd <worktree> && just ci::backend-test-labels app # allow-cd
cd <worktree> && just ci::backend-test-labels rest # allow-cd
```

When rewriting importers and patch strings, edit at the use site. Do not substitute by prefix. A `mock.patch` target must name the module where the code under test looks the name up. If an import is hoisted, the right target moves with it. Where possible, call through the module (`from draft.tasks import hero_tick` then `hero_tick.start_tick_broadcaster(...)`) so the patch target stays stable. Then add an `assert_called()` so a patch that stops intercepting fails loudly. Drop re-exports, so a stale target raises `AttributeError` instead of patching nothing.

### 7. Move routes

Keep paths and `name=`s identical. Include the new app's `urls.py` at the same position the old routes held. Check the old line range for routes that belong to other slices but sit between slice routes: the hero block had the `lobby` include in the middle. WebSocket routes go in `<new_app>/routing.py` and are composed in `backend/asgi.py`.

Dump the URL inventory (pattern, name, callback module) before and after the change. The diff should show only callback module changes.

### 8. Cacheops, signals, admin

- Rename the `CACHEOPS` keys in `backend/backend/settings.py` to `"<new_app>.<model_label>"`. A moved model without a profile raises `ImproperlyConfigured` from `@cached_as`.
- Move receivers to `<new_app>/signals.py` and import it from `AppConfig.ready()`. Module-level imports in signals must be models only from apps in `MODEL_APPS`, or the Celery worker crash-loops. Run `app.tests.test_celery_settings`.
- Move the admin classes. Admin URLs change from `/admin/<source_app>/<model>/` to `/admin/<new_app>/<model>/`.

### 9. Extend the guard

Add a `MovedSlice` to `backend/tests/test_app_boundaries.py` and append it to `MOVED_SLICES`:

- `moved`: fully qualified `(old_module, name)` pairs. Include names the old modules only imported, if tests used to patch them there (for example `("app.consumers", "broadcast_herodraft_state")`).
- `retired_modules`: module paths that no longer exist.
- `model_labels`: lower-case model names. The guard checks `app_label` and `db_table` for each.

Update `ALLOWED_BACK_EDGES[<new_app>]` with each production file in the source app that still imports from the new app, and the names it imports. Test modules are exempt. The guard fails when a listed name is no longer imported, so the list only shrinks. Each listed name also becomes an attribute of that source-app module, so the guard blocks importing it from there (for example `from app.draft_state import HeroDraft`) in every other file.

### 10. Fix stale references

Grep docs and agent config for every retired module path, moved file path and moved test label:

```bash
grep -rn "functions/herodraft\|functions\.herodraft\|herodraft_tick\.py\|tasks\.herodraft_tick\|herodraft_views\|test_herodraft_\|test_stale_connection\|test_signals_post_commit" \
  docs .claude .github backend --include='*.md' --include='*.yml' --include='*.yaml' \
  | grep -v "docs/plans/\|docs/superpowers\|docs/development/app-extraction.md"
```

The grep matches module paths only, so it misses code snippets that show where a moved class is wired. Also check routing, URL and admin snippets that name the moved consumers, views or models:

```bash
grep -rn "app/routing\.py\|app/urls\.py\|HeroDraftConsumer\|HeroDraftSSRView" docs .claude --include='*.md' \
  | grep -v "docs/plans/\|docs/superpowers"
```

Match module paths, not bare names: `herodraft_tick` on its own is also the WebSocket message type, which does not change. Plans under `docs/plans/` are historical; leave them.

### 11. Verify and write the changelog

Run the full verification before opening the PR:

- `manage.py check`, `makemigrations --check --dry-run`, and `sqlmigrate` for each new migration (no SQL).
- Both CI test groups.
- Migrate a copy of a populated pre-move database forward and back (`just docker::db::pull` gets one). Diff `sqlite_master` before and after; only `django_migrations` rows may change, and `django_content_type` must have one row per moved model.
- The guard and the host-side script tests (`just test::slots-unit`).
- An audit of every `mock.patch` target in the slice's tests.
- Playwright specs for the slice (`just test::pw::spec <slice>`).

Add one fragment under `changelog.d/changed/` (see the [changelog workflow](changelog.md)). Mention every visible string that changed: `_meta.label`-derived payload keys, logger names, OpenTelemetry instrumentation scopes and admin URLs.

### 12. Rebase and renumber before merge

Other branches often add the next migration number to the source app. Right before merge, rebase on `main`. If the source app's leaf moved, renumber the move migration to follow the new leaf and update its dependency. Do not add a merge migration. Then re-run `sqlmigrate` and `makemigrations --check`. CI on the PR cannot catch this, and two leaves on `main` break the release-time `makemigrations` and `migrate`.

### 13. Deploy and rollback

**Deploy.** `just dev::release` runs `db::migrate-env release` on the host. That runs `makemigrations <apps>` and then `migrate` from the git checkout, before the new images start. With the migrations committed and `--check` clean, `makemigrations` is a no-op, and `migrate` writes only `django_migrations` rows and the ContentType relabel. The old containers keep working during the window because the tables are unchanged. One brief gap: once the relabel commits, the old containers check permissions under the old app label, so non-superuser staff lose admin access to the moved models until the new images start.

!!! warning "Release-time makemigrations"
    `db::migrate-env` runs `makemigrations` on the prod host before `migrate`. If the host checkout or venv disagrees with the committed state, it can generate a real schema migration on prod. Make sure the checkout is at the release tag and `makemigrations --check` is clean there before you deploy.

**Clean rollback.** Run this before redeploying old code. Each step is state-only or a ContentType relabel, with no DDL:

```bash
python manage.py migrate app 0106
python manage.py migrate discordbot 0012
python manage.py migrate draft zero
```

Use the slice's own migration names.

These commands run with the new code, so each `migrate` fires `post_migrate`, which re-creates `(<new_app>, <model>)` ContentTypes and their permissions next to the relabelled `(<source_app>, <model>)` rows. The new rows hold no grants and no admin log entries. Delete them once the old code is running, before any later forward migrate. If you skip this, the next deploy's relabel finds the destination rows already there and skips them (`contenttype_relabel_skipped`), and every existing grant stays on the stale `<source_app>` rows. Delete only the slice's moved models, by name:

```bash
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='<new_app>', model__in=[<moved models, lower-case>]).delete()"
```

For the hero draft slice that is `app_label='draft', model__in=['herodraft', 'draftteam', 'herodraftround', 'herodraftevent']`.

!!! danger "Never delete by `app_label` alone"
    `ContentType.objects.filter(app_label='<new_app>').delete()` also hits every other model in the destination app, including slices moved earlier. The delete cascades through `auth_permission`, `auth_user_user_permissions` and `auth_group_permissions`, so their real grants are wiped, and `django_admin_log.content_type` is set to NULL for their log entries. Always filter on the moved model names.

**Code-only rollback** (redeploy the old image without unmigrating) also works. The old code ignores migrations it does not know, and the schema is identical. But its `post_migrate` recreates `(<source_app>, <model>)` ContentTypes next to the relabelled `(<new_app>, <model>)` rows, and permission grants stay on the new rows. To get back to one row per model, reconcile by hand. Repoint `auth_permission` (and through it `auth_user_user_permissions` and `auth_group_permissions`) and `django_admin_log` from the duplicate ContentType to the surviving one, then delete the duplicate.

## Notes for the team-draft slice

- `draft/tests/test_hero_timer_options.py` imports `app.tests.teamdraft_fixtures.TimedDraftFixture`. Move that fixture into `draft/tests/` with the team-draft code and remove the test-only `draft -> app.tests` edge.
- Add a `TEAM_DRAFT` entry to the guard. If team draft moves completely, the `ALLOWED_BACK_EDGES["draft"]` entries for `app/draft_state.py` and `app/views_main.py` should go away with it.
- The test-db image hash covers `backend/*/models/*.py`, so any change to `draft/models/` busts the cache and CI runs a fresh populate.
