# Backend App Extraction

`backend/app` started as the only Django app and still holds most of the backend. We are splitting it into domain apps one slice per PR, models included. Each PR moves one slice, and `app/` only ever gets smaller.

The first slice moved the hero draft family into the new `draft` app, and the second moved the team draft family into the same app. The third moved `Organization`, `OrgLog` and the org permissions into the existing `org` app, the fourth moved the league domain into the existing `league` app, and the fifth moved `Tournament`, `Team`, `Game`, `TeamLog` and all tournament, team and game code into the new `tournament` app in three stacked PRs. This page is the recipe they followed, written so later slices can repeat it step by step.

Planned slices, in order:

| Slice | Source app | Target app |
|-------|-----------|------------|
| Hero draft (done) | `app` | `draft` |
| Team draft (done: `Draft`, `DraftRound`, `DraftEvent`, `DraftOptions`, teamdraft/shuffle/draft_picks, `draft_tick`, `teamdraft_tick`) | `app` | `draft` |
| Organization (done: `Organization`, `OrgLog`, org permissions) | `app` | `org` |
| League (done: `League`, `LeagueRating`, `LeagueMatch`, `LeagueMatchParticipant`, `LeagueLog`, league permissions, rating and match services) | `app` | `league` |
| Tournament (done, three PRs: domain layer, HTTP/WebSocket surface, then `Tournament`, `Team`, `Game`, `TeamLog`) | `app` | `tournament` |
| Bracket models (later: `TournamentBracket`, `BracketSlot`; bracket views and URL wiring already live in `tournament`) | `bracket` | `tournament` |
| Users, profile claims, jokes (later) | `app` | to be decided |

`CustomUser` stays in `app` (it is `AUTH_USER_MODEL`).

After the tournament slice, `app/models.py` holds `CustomUser`, `PositionsModel`, `ProfileClaimRequest` and `Joke`. The `"league.League"` and `"league.LeagueUser"` lazy strings left with `Tournament`, `Game` and `Team`. Two lazy `"org.Organization"` strings remain, on `CustomUser.default_organization` and `ProfileClaimRequest.organization`. Lazy strings are not import edges, so they are not in `ALLOWED_BACK_EDGES`. `app.models` still re-exports `GameType` from `common.game` for its many importers outside `app`.

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

Two more inventories:

- **Build the guard's `moved` set from the patch strings.** For each module that loses code, grep its patch targets (single- and multi-line, as above, plus `patch.object(<module>, ...)` on imported module objects). Every patched name that leaves the module goes in `moved`. A name that stays in the old module but is patched for moved code (for example a module-level `log`) cannot go in `moved`, because its definition would trip the guard. Its patch sites need a use-site retarget instead.
- **Find other apps' migrations that name the moved models.** These must run before the source app's move migration (see "Cross-app data migrations" below). The guard enforces it, but find them before you write the dependencies:

```bash
grep -rnE "get_model\(\s*['\"]app['\"]" $B/*/migrations/*.py
grep -rniE "['\"]app\.(draft|draftround|draftevent|draftoptions)['\"]" $B/*/migrations/*.py
```

### 2. Create or extend the target app

For a new app:

- Add `backend/<new_app>/` with `apps.py`, and empty `models/__init__.py`, `migrations/__init__.py`, `tests/__init__.py`.
- Add it to `MODEL_APPS` in `backend/config/installed_apps.py`. Celery installs only `MODEL_APPS`.
- Add it to the `apps` list in `just/db/mod.just` **and** to `APPS` in `scripts/slot_tests/test_just_recipes.py`. `scripts/slot_tests/test_app_lists.py` fails if any `MODEL_APPS` entry with migrations is missing from either list.
- Add `backend/<new_app>/**` to the matching label in `.github/labeler.yml`.

Not every source app is `app`:

- `bracket` is its own app (label `bracket`, `bracket.apps.BracketConfig`, tables `bracket_*`). The later bracket-models slice moves `TournamentBracket` and `BracketSlot` into `tournament` with `source_app="bracket"`, state-only, and keeps the `bracket_*` tables.

To extend an existing app (as the organization slice did with `org`):

- Check it is already in `MODEL_APPS`, the `just` app lists and the labeler. If not, add it as for a new app.
- If signal receivers move, add a `ready()` to its `AppConfig` that imports `<app>.signals` (`org/apps.py`, `draft/apps.py`).
- Fit the moved code into the app's existing module layout. `org` keeps flat `models.py` plus `models_*.py` files, so `Organization` and `OrgLog` went into `org/models.py`, not a new `models/` package.
- Check that the app's model files are covered by the test-db hash globs (see the last lesson below). `org`'s flat `models_*.py` files were not, until the organization slice added `backend/*/models_*.py`.

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

After adding or renumbering a migration, update that app's `migrations/max_migration.txt` (django-linear-migrations).

Every new migration in an app other than the source app also lists its own app's previous leaf as a dependency, or that app ends up with two leaf nodes. Check that each touched app has exactly one leaf afterwards (`backend/league/tests/test_league_move_migration.py` pins this with `test_one_leaf_per_app`).

The ContentType relabel is required. Without it, `post_migrate` creates new permission rows that nobody holds, and the existing user and group grants stay behind on stale rows. The relabel must be symmetric and defensive: for each model, skip it (and log once) when the destination row already exists, in both directions. Then neither direction can hit `UNIQUE(app_label, model)`. See `backend/app/migrations/0108_move_hero_draft_models_to_draft.py`.

Move migrations log with `structlog.get_logger(__name__)`, never `telemetry.logging`: a historical migration must not import app code, and stdlib `extra=` fields are dropped from rendered logs.

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

**Slice size.** Split a slice into stacked PRs when it has a separable shared-infrastructure move (prep and infra in one PR, domain code and models in the next), or when the diff passes roughly 60 non-test files. The team draft slice is the worked example: the prep commits plus the `draft_tick` and `consumers_base` moves form a self-contained prefix that touches no models or migrations.

When the code surface alone passes the threshold, use three stacked PRs cut from one branch, as the tournament slice did: (a) prep fixes, the empty app and the domain layer (permissions, services, signals, state and listing helpers, internal client, schemas, management commands); (b) the HTTP and WebSocket surface (serializers, views, URL wiring, consumers, SSR, internal endpoints, admin); (c) the model move. The models stay in the source app through (a) and (b), so every PR leaves the tree importable and adds no migrations until (c).

A split creates interim same-name twins: a name that moves in (a) can still be defined in the source app by a module that only moves in (b), for example the worker HTTP client `get_tournament_for_task` and the internal view of the same name. Record each twin in `ALLOWED_NAME_COLLISIONS` with the PR that removes it; `test_name_collisions_not_stale` forces the removal.

After each commit, run the touched-name sweep (every test module that mentions the slice):

```bash
grep -rlE 'HeroDraft|DraftTeam|herodraft|HERODRAFT' <worktree>/backend --include='test*.py'
```

Convert the paths to dotted labels and pass them to `just test::run`. For commits that move code, also run all three CI groups:

```bash
cd <worktree> && just ci::backend-test-labels app # allow-cd
cd <worktree> && just ci::backend-test-labels migrations # allow-cd
cd <worktree> && just ci::backend-test-labels rest # allow-cd
```

When rewriting importers and patch strings, edit at the use site. Do not substitute by prefix. A `mock.patch` target must name the module where the code under test looks the name up. If an import is hoisted, the right target moves with it. Where possible, call through the module (`from draft.tasks import hero_tick` then `hero_tick.start_tick_broadcaster(...)`) so the patch target stays stable. Then add an `assert_called()` so a patch that stops intercepting fails loudly. Drop re-exports, so a stale target raises `AttributeError` instead of patching nothing.

### 7. Move routes

Keep paths and `name=`s identical. Include the new app's `urls.py` at the same position the old routes held. Check the old line range for routes that belong to other slices but sit between slice routes: the hero block had the `lobby` include in the middle. WebSocket routes go in `<new_app>/routing.py` and are composed in `backend/asgi.py`.

Dump the URL inventory (pattern, name, callback module) before and after the change. The diff should show only callback module changes.

Commit an `<new_app>/tests/test_<new_app>_routes.py` that resolves every moved path to its new module and `url_name`, and checks that the API root still lists any moved router prefix (`backend/league/tests/test_league_routes.py`).

### 8. Cacheops, signals, admin

- Rename the `CACHEOPS` keys in `backend/backend/settings.py` to `"<new_app>.<model_label>"`. A moved model without a profile raises `ImproperlyConfigured` from `@cached_as`.
- Move receivers to `<new_app>/signals.py` and import it from `AppConfig.ready()`. Module-level imports in signals must be models only from apps in `MODEL_APPS`, or the Celery worker crash-loops. Run `app.tests.test_celery_settings`.
- Move the admin classes. Admin URLs change from `/admin/<source_app>/<model>/` to `/admin/<new_app>/<model>/`.

### 9. Extend the guard

Add a `MovedSlice` to `backend/tests/test_app_boundaries.py` and append it to `MOVED_SLICES`:

- `moved`: fully qualified `(old_module, name)` pairs. Include names the old modules only imported, if tests used to patch them there (for example `("app.consumers", "broadcast_herodraft_state")`).
- `retired_modules`: module paths that no longer exist. Every top-level class and function a retired module defined also goes into `moved`, under the old module path. When a module is split (some names stay in the source app under another module, some leave), names that stay in the source app are never listed in `moved`, because their definition there would trip the redefinition check; names that leave for any other app are listed. `app/permissions_tournament.py` is the example: `request_user` went to `app.permissions` and is not listed, while `has_event_staff_access` went to `events.permissions` and is. The anywhere-redefinition check reads only `moved`, so an unlisted name could be redefined in the source app unnoticed. `test_retired_module_defs_listed_in_moved` enforces this: it reads each retired module's new home (the same path under the new app, or its entry in `RETIRED_MODULE_HOMES`, where `None` marks a module renamed within the source app) and fails on any top-level class or function missing from `moved`.
- `model_labels`: lower-case model names. The guard checks `app_label` and `db_table` for each.
- `move_migration`: `(source_app, name)` of the source app's move migration. The guard scans every other app's migrations for references to the moved models under the source label and requires each one to be an ancestor of this migration.
- `cached_labels`: the moved models that have a `CACHEOPS` profile. The guard checks that `"<new_app>.<label>"` is present.

Do not touch `GuardSelfTests` to add a slice. They run against a synthetic fixture slice and back-edge map, not the live ones.

The guard also flags `get_model("<source_app>", "<Moved>")` outside migrations and migration tests, and any top-level class or function in the source app named after a moved name. Management-command `Command` classes in `*.management.commands.*` modules are exempt from that redefinition check, since every command module defines one.

Lazy references are matched by label prefix, case-insensitively: `"<source_app>.<Model>"` itself, M2M through-model sender strings such as `"app.Team_members"`, and dotted field keys such as `"app.TeamLog.team"` all count as references to the moved model and must be retargeted with it. Prefer deriving such keys from `_meta.label` over writing literals.

Committed tests never name a retired module path as a string, not even to assert its absence: the string back-door check walks test modules too. Assert the new home instead (`obj.__module__ == "<new_app>.<module>"`) and rely on `test_retired_modules_are_gone` for the absence. A name that genuinely collides goes in `ALLOWED_NAME_COLLISIONS` with a reason (for example the worker HTTP helper `create_herodraft_for_game` in `app/internal_client`).

Update `ALLOWED_BACK_EDGES[<new_app>]` with each production file in the source app that still imports from the new app. Each entry is a `BackEdge(names, reason, type_only)`. Test modules are exempt. The rules:

- The list must match reality exactly. The guard fails on an unlisted file or name and on a listed name that is no longer imported.
- Every entry carries a non-empty `reason`.
- The list may grow, but only for class-definition-time uses, code owned by a later slice (tournament, Team) or cross-domain aggregate endpoints (`home_stats` in `app/views_main.py` counts leagues next to tournaments, games and organizations). An unlisted edge the guard reports is a design question, not something to add without thought.
- Names imported only under `if TYPE_CHECKING:` go in `type_only`. A runtime import of a `type_only` name is a violation.

Each listed name also becomes an attribute of that source-app module, so the guard blocks importing it from there (for example `from app.views_main import DraftRound`) in every other file.

Derive the entries from the guard's own output rather than writing them by hand. Between commits, an edge that exists only until a later commit can be listed with a reason starting `TEMP`; none may be left by the guard commit.

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

Hard-coded path lists in code and config also name old modules and files. Grep for the old file paths, not only the dotted module names, and check each of these:

- `BROADCAST_CALL_SITES` and similar module-name tuples in tests
- `SCAN_TARGETS` in `user/tests/test_cacheops.py`
- `RouteResolutionTests` expected modules
- the logger-level overrides in `backend/settings.py`
- test globs in `just/test/backend.just`
- `.github/labeler.yml`

### 11. Verify and write the changelog

Run the full verification before opening the PR:

- `manage.py check`, `makemigrations --check --dry-run`, and `sqlmigrate` for each new migration (no SQL).
- All CI test groups. Record the `app`, `migrations` and `rest` backend-test durations on the base branch and on the slice branch in the PR description. If the slower group grows by more than about 20%, rebalance `just ci::backend-test-labels` (for example with a third `draft` group) in that PR or a follow-up.
- Migrate a copy of a populated pre-move database forward and back (`just docker::db::pull` gets one). Diff `sqlite_master` before and after; only `django_migrations` rows may change, and `django_content_type` must have one row per moved model.
- The guard and the host-side script tests (`just test::slots-unit`).
- An audit of every `mock.patch` target in the slice's tests.
- Playwright specs for the slice (`just test::pw::spec <slice>`).

Add one fragment under `changelog.d/changed/` (see the [changelog workflow](changelog.md)). Mention every visible string that changed: `_meta.label`-derived payload keys, logger names, OpenTelemetry instrumentation scopes and admin URLs.

### 12. Merge `main` and renumber before merge

Other branches often add the next migration number to the source app. Right before merge, merge `origin/main` into the branch (do not rebase a stacked or shared branch). If the source app's leaf moved, renumber the move migration to follow the new leaf and update its dependency. Do not add a merge migration. Then re-run `sqlmigrate` and `makemigrations --check`. CI on the PR cannot catch this, and two leaves on `main` break the release-time `makemigrations` and `migrate`.

### 13. Deploy and rollback

**Deploy.** `just dev::release` pulls the release images, stops the release stack, then runs `db::migrate-env release` on the host before it starts the new images. `db::migrate-env` runs `makemigrations <apps>` and then `migrate` from the git checkout. With the migrations committed and `--check` clean, `makemigrations` is a no-op, and `migrate` writes only `django_migrations` rows and the ContentType relabel. No old container runs while the relabel commits, so there is no window where staff permissions are checked under the old app label.

!!! warning "Release-time makemigrations"
    `db::migrate-env` runs `makemigrations` on the prod host before `migrate`. If the host checkout or venv disagrees with the committed state, it can generate a real schema migration on prod. Make sure the checkout is at the release tag and `makemigrations --check` is clean there before you deploy.

**Clean rollback.** Run this before redeploying old code. Each step is state-only or a ContentType relabel, with no DDL:

```bash
python manage.py migrate app 0107
python manage.py migrate discordbot 0012
python manage.py migrate draft zero
```

Use the slice's own migration names. For the hero draft slice this is no longer DDL-free: `draft zero` also unapplies `draft/0002_herodraftchat`, which drops the hero draft chat tables.

These commands run with the new code, so each `migrate` fires `post_migrate`, which re-creates `(<new_app>, <model>)` ContentTypes and their permissions next to the relabelled `(<source_app>, <model>)` rows. The new rows hold no grants and no admin log entries. Delete them once the old code is running, before any later forward migrate. If you skip this, the next deploy's relabel finds the destination rows already there and skips them (`contenttype_relabel_skipped`), and every existing grant stays on the stale `<source_app>` rows. Delete only the slice's moved models, by name:

```bash
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='<new_app>', model__in=[<moved models, lower-case>]).delete()"
```

For the hero draft slice that is `app_label='draft', model__in=['herodraft', 'draftteam', 'herodraftround', 'herodraftevent']`.

For the team draft slice, the clean rollback is:

```bash
python manage.py migrate app 0108
python manage.py migrate discordbot 0013
python manage.py migrate draft 0003
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='draft', model__in=['draft', 'draftround', 'draftevent', 'draftoptions']).delete()"
```

Here the model name `draft` is the same as the app label. The `model__in` filter handles that correctly; it is not a typo.

For the organization slice, the clean rollback is:

```bash
python manage.py migrate app 0110
python manage.py migrate events 0034
python manage.py migrate opsnotices 0002
python manage.py migrate org 0013
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='org', model__in=['organization', 'orglog']).delete()"
```

`migrate app 0110` reverses the relabel first. Never delete `app_label='org'` alone: `org` holds many other models (`OrgUser`, `OrgFeature`, `OrgSettings` and more), and the delete would cascade through all their permissions and grants. If the prep PR (3a) shipped and the model-move PR (3b) is rolled back, 3a stays: it has no migrations.

For the league slice, the clean rollback is:

```bash
python manage.py migrate app 0111
python manage.py migrate events 0035
python manage.py migrate org 0016
python manage.py migrate league 0002
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='league', model__in=['league', 'leaguerating', 'leaguematch', 'leaguematchparticipant', 'leaguelog']).delete()"
```

`migrate app 0111` reverses the relabel first. `org 0016` is the migration before `org/0017_retarget_default_league_to_league`; going further back would also unapply unrelated `org` migrations. Never delete `app_label='league'` alone: `leagueuser` is a pre-existing `league` model, and deleting its ContentType cascades its permissions and grants. If the prep PR (4a) shipped and the model-move PR (4b) is rolled back, 4a stays: it has no migrations.

For the tournament slice, the clean rollback is:

```bash
python manage.py migrate app 0114
python manage.py migrate bracket 0002
python manage.py migrate discordbot 0014
python manage.py migrate draft 0005
python manage.py migrate events 0038
python manage.py migrate league 0003
python manage.py migrate lobby 0004
python manage.py migrate org 0020
python manage.py migrate steam 0008
python manage.py migrate tournament zero
python manage.py shell -c "from django.contrib.contenttypes.models import ContentType; ContentType.objects.filter(app_label='tournament', model__in=['tournament', 'team', 'game', 'teamlog']).delete()"
```

`migrate app 0114` reverses the relabel first. Each other app goes back only to the migration before its `retarget` migration, so no unrelated migration is unapplied. `tournament` has no other models yet, but the delete still filters on model names, as later slices may add some. The 5a and 5b PRs have no migrations, so they stay if only 5c is rolled back.

!!! danger "Never delete by `app_label` alone"
    `ContentType.objects.filter(app_label='<new_app>').delete()` also hits every other model in the destination app, including slices moved earlier. The delete cascades through `auth_permission`, `auth_user_user_permissions` and `auth_group_permissions`, so their real grants are wiped, and `django_admin_log.content_type` is set to NULL for their log entries. Always filter on the moved model names.

**Code-only rollback** (redeploy the old image without unmigrating) also works. The old code ignores migrations it does not know, and the schema is identical. But its `post_migrate` recreates `(<source_app>, <model>)` ContentTypes next to the relabelled `(<new_app>, <model>)` rows, and permission grants stay on the new rows. To get back to one row per model, reconcile by hand. Repoint `auth_permission` (and through it `auth_user_user_permissions` and `auth_group_permissions`) and `django_admin_log` from the duplicate ContentType to the surviving one, then delete the duplicate.

## What the team-draft slice learned

- **Cross-app data migrations need an explicit edge.** Any other app's migration that calls `apps.get_model("<source_app>", "<Moved>")` must be an ancestor of the source app's move migration. `events/0024` read `app.DraftOptions`, so `app/0109` depends on it; without that edge a fresh `migrate` can fail with `LookupError`. The guard's ancestry check (`move_migration`) now enforces this for every slice.
- **Class-definition-time uses in the source app stay until their consumer moves.** A choices enum such as `DraftStyles`, or a serializer class attribute such as `TournamentSerializer.draft`, cannot be fixed by moving the dependency. Leave it, and record the edge as a back-edge with a reason.
- **Method-body uses of a moved model inside a source-app model** resolve it with `self._meta.get_field("<fk>").related_model`, with a `TYPE_CHECKING` import for the annotation (`Tournament.get_draft_options`). The guard pins that import as `type_only`.
- **Shared infrastructure moves with the slice that owns it.** Split off the parts other domains still need first: `consumer_db` went to `app/consumer_db.py` so `TournamentConsumer` and both draft consumers share one executor. Keep a module's name when many patch strings depend on it (`draft/tasks/draft_tick.py`).
- **Keep DRF router registrations in `backend/urls.py`**, importing the viewsets from the new app, so the API root listing does not change.
- **Logger-level overrides follow the code.** The INFO overrides in `backend/settings.py` name module loggers. When code moves, add the new logger names, and keep an old one only if that module still logs. Otherwise those INFO lines are dropped whenever `LOG_LEVEL` is above INFO, and no test notices because the test env runs at DEBUG.
- **Tournament code that reads draft tables keeps its back-edges.** The slice 1 note expected the `app/draft_state.py` and `app/views_main.py` entries to disappear. They did not: the tournament prefetch plan (now `app/tournament_state.py`) and the `views_main` cache dependencies are tournament code that legitimately reads draft tables. They go when the tournament slice moves.
- **Rename source-app modules whose name would attract the moved code back.** `app/draft_state.py` became `app/tournament_state.py` once the draft functions left it.
- **Test-only cross-app edges are stated, not claimed gone.** `draft/tests` imports nothing from `app.tests`. `app/tests` imports `draft.tests.team_fixtures` and `draft.tests.ws_helpers`, the same direction as the production back-edges.
- **Team-domain helpers stay with Team** even when draft code is their only caller. `app/services/team_references.py` stays in `app`, and `draft/services/team_reset.py` imports it forward. `app/services/team_management.py` also stays; its imports of the team draft models and `emit_event` are a recorded back-edge.
- The test-db image hash covers `models.py`, `backend/*/models/*.py`, `backend/*/models_*.py` and every migration, so any change to `draft/models/` busts the cache and CI runs a fresh populate.

## What the organization slice learned

- **A mixed helper module splits.** The domain part moves, and the remainder is renamed after what will remain once the next slice leaves: `app/permissions_org.py` became `org/permissions.py` plus `app/permissions_tournament.py`.
- **Serializers used at class-definition time in the source app stay until their consumer moves**, even when their own domain has left. `OrganizationsSerializer` stays in `app.serializers` because `LeaguesSerializer` (still in `app`) declares it as a field. `LeagueSerializer`, now in `league.serializers`, imports it forward from `app.serializers`.
- **Shared pipelines with one front door per domain move whole when the last foreign door leaves.** `app/views/csv_import.py` serves both the org and the tournament import, so it stays in `app` until the tournament slice.
- **Check whether the moved models are registered in admin before promising admin URL changes.** Neither `Organization` nor `OrgLog` has an admin, so no admin URL changed.
- **Inbound FK retargets inside the target app go in the target app's create migration, after the `CreateModel`s.** `org/0014` creates `Organization` and `OrgLog` and then retargets the nine `org` FKs; `events/0035` and `opsnotices/0003` depend on it, and `app/0111` depends on all three.
- **Expect a long first back-edge list when the target app already exists.** The guard counts pre-existing source-to-target imports (`app` importing `org.models.OrgUser`, `org.membership` and so on) as back-edges, so the first `ALLOWED_BACK_EDGES["org"]` list is long by construction and shrinks as later slices leave `app`.
- **Split slices into an existing app as prep plus model move.** The prep PR adds the slice's guard entry with the code-move `moved` names, `retired_modules`, empty `model_labels`/`cached_labels` and the full pre-existing back-edge list. The model-move PR adds the model labels, cache labels and model `moved` pairs. That keeps the prep PR protected while it sits on `main`.
- **An existing target app's migrations are not exempt from the ancestry check; only the source app's are.** `org` already had migrations naming `app.organization`. A later `org` migration cut from pre-move `main` that still points at `app.organization` must be an ancestor of `app/0111`, or `migrate` fails with an unresolved lazy reference. `org/0013_conduct` landed on `main` mid-slice with two FKs to `app.organization`; `org/0014` depends on it, which puts it before the move.
- **A source-app migration that alters a moved model lands in the move's `CreateModel`.** `app/0110_orglog_conduct_actions` added three `OrgLog.action` choices on `main` while the slice was open. The move migrations follow it (`org/0014` and `app/0111` depend on it), and `org/0014`'s `CreateModel(OrgLog)` carries the same choices, so `makemigrations --check` stays clean.
- **When a source module is renamed, carry every earlier slice's `moved` entries for it over to the new path.** The guard's redefinition and patch-string checks are keyed on the module path, so `TEAM_DRAFT.moved` lists `CanEditDraft` and `CanEditDraftRound` under both `app.permissions_org` and `app.permissions_tournament`.
- **Lazy FK strings from the source app to the new app are not import edges.** `"org.Organization"` in `app/models.py` is not in `ALLOWED_BACK_EDGES`. List such strings in the slice's spec and in the slice table note above.

## What the league slice learned

- **A mutual FK between the target app and another non-source app resolves through ordering.** `League.organization` and `Organization.default_league` point at each other. The order `org/0014 → app/0111 → league/0003 → org/0017 → app/0112` handles it with no `RemoveField`: `league/0003` creates `League` pointing at `org.Organization`, `org/0017` retargets `default_league` to `league.League`, and only then does `app/0112` delete the old state.
- **The rollback ContentType delete lists only the moved models.** It must never cover the target app's own pre-existing models (`leagueuser`).
- **Services with no production caller still move whole with their domain.** `LeagueMatchService` and the rating systems have no production caller, but deleting them is a separate product decision, not part of a move.
- **Eager package re-exports are dropped, not carried over.** `app/services/__init__.py` re-exported the league services; it now holds only its docstring, and the new `league/services/` package has an empty `__init__`.
- **Serializers embedded in source-app serializers stay even when their domain moves.** `LeaguesSerializer` and `LeagueMinimalSerializer` stay in `app.serializers`. `LeagueSerializer`, which only the moved view uses, moved.
- **Revisit the slice table during recon.** Ratings, matches and league logs were listed as separate later slices but belonged to the league domain, so they moved with it.

## What the tournament slice learned

- **Three stacked PRs for a slice whose code surface alone passes the threshold.** 5a moved the domain layer (permissions, services, signals, state and listing helpers, internal client, schemas, management commands), 5b the HTTP and WebSocket surface (serializers, views, URL wiring, consumer, SSR, internal endpoints, admin), and 5c the models. 5a and 5b add no migrations, so each PR can merge and roll back on its own.
- **A new target app can be in `MODEL_APPS` with no `migrations/` until its model PR.** `notifications` is the precedent. The `just/db/mod.just` and `scripts/slot_tests` app lists follow the migrations directory, so `tournament` joined them only in 5c.
- **Put the new app in `MODEL_APPS` where the source app is.** `tournament` sits right after `app`, so the moved `Game` and `Team.members` receivers keep their dispatch order relative to `draft` and `lobby` receivers. `tournament/tests/test_signal_order.py` pins the order with literals captured before the move.
- **M2M through-model sender strings and `_meta.label` field keys are references to the moved model.** `"app.Team_members"` senders and the `"app.TeamLog.team"` key in `team_references` had to follow the model. `team_references` now derives its keys from `_meta.label`, and the guard matches lazy labels by prefix.
- **Split retirements list only the names that leave the source app.** When `app/permissions_tournament.py` was split, `request_user` stayed in `app.permissions` and is not in `moved`; `has_event_staff_access` went to `events.permissions` and is.
- **Code-first PRs leave interim twins in the source app.** Record each in `ALLOWED_NAME_COLLISIONS` with the PR that removes it. All of them were gone by the end of 5b.
- **A function-local import can guard the Celery app set, not only a cycle.** `build_users_dict_with_org` keeps `from app.user_cache import serialize_users_core` inside the function because `app.user_cache` loads `user.models`, which Celery does not install. Before hoisting, check whether the imported module pulls a model from an app outside `MODEL_APPS`. `test_celery_settings` now boots the worker's default modules and asserts `user.models` and `bracket.models` stay unloaded.
- **Leftovers waiting on the slice's domain move with it.** `OrganizationsSerializer`, `LeaguesSerializer` and `LeagueMinimalSerializer` stayed in `app.serializers` after the org and league slices only because tournament serializers embedded them. The serializer split moved them to `org.serializers` and `league.serializers` in the same PR.
- **Enums that other apps' models import at module level go in a dependency-free `choices.py`.** `tournament/choices.py` imports only Django, so `events.models` and `bracket.models` can import `GameMode`, `DotaLobbyMode` and `DraftStyles` without loading `tournament.models`.
- **Unused back-compat re-exports are deleted, not moved.** `app.schemas` re-exported `discordbot` and `events` schemas and kept four aliases nobody imported. Dropping them also removed a function-local import and a forward-ref rebuild workaround in `events/schemas.py`.
- **Re-list the inbound FKs after every merge of `main`.** `org/0020_leadership` landed mid-slice with `EventCaptain.team`, so the model move needed a tenth migration (`org/0021_retarget_tournament_models`) that the plan had not listed.
- **Never order a payload by model label.** `team_usage` sorted by `_meta.label`, so relabelling `Game` moved its row in the draft force-reset dialog. It now sorts by display label with a fixed order (`_USAGE_ORDER`), pinned by `test_usage_ordered_by_display_label_not_app_label`. The `model` values still change from `app.*` to `tournament.*`; the changelog lists that.
- **Each move adds nodes that existing migration tests step through.** Run back to back on one host, the `migrations` CI group took 403s for 31 tests on `main` and 571s for 37 tests after 5c (+41%). The new tournament move test accounts for about 60s. The other 107s (+27%) come from existing tests that roll `org` or `user` back and now unapply ten more state-only migrations. It is now the slowest backend group, so split `migrations` into two matrix groups in `just ci::backend-test-labels` before slice 6 adds more nodes, for example `draft`, `league` and `tournament` in one group and `org` and `user` in the other (about 285s and 330s with setup, close to the `rest` group).
