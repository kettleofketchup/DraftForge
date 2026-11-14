---
name: testing
description: DraftForge test infrastructure for writing backend unit tests, Playwright E2E tests, and managing test data population. This skill should be used when writing new tests, adding test fixtures, creating populate functions for new features, adding Playwright E2E specs, using login/auth fixtures, creating test users/orgs/leagues/tournaments, or understanding the test data architecture. Covers backend Django tests via Docker, Playwright config (projects, workers, sharding), test auth endpoints that expose backend login to frontend, feature-isolated test data patterns, and per-worktree test stack slots (which port, two worktrees, test stack slot, which URL, slot-reap).
---

# DraftForge Testing Infrastructure

## Self-Updating

This skill documents live code. When modifying test infrastructure, update the relevant reference file.
To verify current state, read the source files referenced in each section.

## Critical Rules

1. **Always use `data-testid` selectors** in Playwright tests and demos. Never use `getByLabel`, `getByText`, or `getByRole('combobox')` for element interaction. See [playwright-fixtures.md](references/playwright-fixtures.md) for the full policy and exceptions.
2. **Use `postWithCsrf`/`patchWithCsrf`** for all POST/PATCH calls to DRF ViewSet endpoints (not test endpoints). See [playwright-fixtures.md](references/playwright-fixtures.md) for CSRF handling.

## Architecture Overview

Two-layer test data system:
1. **Data definitions** (`backend/tests/data/`) - Pydantic models (TestUser, TestOrganization, TestLeague, TestTeam, TestTournament)
2. **Populate functions** (`backend/tests/populate/`) - Create DB records from data definitions

Backend exposes `/api/tests/*` endpoints (TEST=true only) so Playwright can login, reset state, and create test-specific data.

## Key Principle: Feature-Isolated Test Data

Each feature's E2E tests MUST use dedicated test data. Never reuse another feature's org/league/tournament.

See [references/feature-isolation.md](references/feature-isolation.md) for the full pattern.

## Running Tests

```bash
# Backend (Docker; test::run passes --entrypoint "" to bypass daphne)
just test::run 'python manage.py test app.tests.test_csv_import -v 2'
# Same thing through the slot-aware compose wrapper (never raw docker compose)
just test::compose run --rm --entrypoint "" backend python manage.py test app.tests.test_csv_import -v 2
# Whole backend suite, exactly what CI runs (no labels = discover all of backend/)
just test::run 'python manage.py test -v 2'
# CI discovers new modules automatically; write TestCase/SimpleTestCase classes,
# not bare pytest functions (the Django runner skips those).

# Playwright
just test::pw::headless              # All tests
just test::pw::spec csv-import       # Specific suite
just test::pw::ui                    # Interactive UI mode

# Full setup (down, update, build, populate, up)
just test::setup

# Repopulate test data only
just db::populate::all
```

## Test Stack Slots (which port, two worktrees)

Every worktree runs its own test stack in a slot: slot 0 is project `df` on
`https://localhost`, slot N ≥ 1 is `df-sN` on `https://localhost:1N443`.

- Run `just test::slots` (read-only) or `just test::slot` to find the URL. **Never hardcode `https://localhost`** in tests, fixtures or commands; Playwright imports `BASE_URL` / `API_URL` from `fixtures/base-url.ts`.
- Use `just test::compose <args>` for any compose command, never raw `docker compose` or `docker exec <name>`.
- Slots N ≥ 1 run without the Discord bot, celery beat and real Discord/Steam tokens unless `just test::background on`.
- `just test::slot-reap`, `just test::slot-claim` and `just test::slot-release --slot N` need no user approval. Before using one on another worktree's slot, verify no agent is working in or testing against it (owner worktree activity, the project's containers and logs, test processes with that cwd, peer Claude sessions). If in doubt, don't touch it.
- Slots idle more than 12h are reaped automatically on the next allocation; `just test::slot-reap --stale` does it now.
- The 18-dota-lobby specs drive a simulated dota_lobby, the profile-gated `dota-lobby` service: `just test::dota-lobby up` (image and pinned release tag in [test-stack-slots.md](references/test-stack-slots.md)). Without it, the specs that need it skip (03 uses a seeded lobby row instead); with it running, `just test::pw::dota-lobby` fails rather than skips if it never becomes available.

Commands, externals policy and troubleshooting: [test-stack-slots.md](references/test-stack-slots.md).

## Cacheops and Test State Resets

Django cacheops is active in the test environment (1-hour TTL for Organization, League, etc.). **M2M changes (`.add()`, `.remove()`, `.clear()`) do NOT auto-invalidate cacheops cache.**

When writing test reset endpoints or backend views that modify M2M fields:

```python
from cacheops import invalidate_obj

org.admins.clear()
org.admins.add(admin_user)
invalidate_obj(org)  # REQUIRED after M2M changes
```

Without `invalidate_obj()`, subsequent GET requests return stale cached data — a common cause of flaky E2E tests where state resets appear to not take effect.

See [references/backend-test-endpoints.md](references/backend-test-endpoints.md) for the full pattern.

## Reference Files

| Reference | When to read |
|-----------|-------------|
| [populate-system.md](references/populate-system.md) | Adding test data, new populate functions, understanding data models |
| [playwright-fixtures.md](references/playwright-fixtures.md) | Writing E2E tests, using login fixtures, auth patterns |
| [backend-test-endpoints.md](references/backend-test-endpoints.md) | Adding new test API endpoints, understanding backend-frontend test bridge |
| [feature-isolation.md](references/feature-isolation.md) | Creating dedicated test data for a new feature's E2E tests |
| [playwright-config.md](references/playwright-config.md) | Test runner config, projects, workers, sharding, timeouts |
| [mobile-iteration-workflow.md](references/mobile-iteration-workflow.md) | Iterating on mobile overflow / hydration regressions across the `brand`, `ui-styling`, `i18n-react`, `playwright` skills |
| [layout-overlap.md](references/layout-overlap.md) | A red `layout` project: overlapping or clip-escaping content, the quarantine file, the detector self-test |

## Quick Reference: Current Test Data

| Entity | Name | PK | steam_league_id |
|--------|------|----|-----------------|
| Org | DTX | 1 | - |
| Org | Test Organization | 2 | - |
| Org | CSV Import Org | 3 | - |
| Org | Events Test Org | 7 | - |
| League | DTX League | 1 | 17929 |
| League | Test League | 2 | 17930 |
| League | CSV Import League | 3 | 17931 |
| League | Events Test League | 7 | 17935 |
| Org / League | Lobby Test Org / Lobby Test League | auto (look up by name) | 17940 |
| Org / League | Features Test Org / Features Test League (both paid features unlocked) | 30 | 17941 |
| Org / League | Locked Features Org / Locked Features League (both locked) | 31 | 17942 |
| Org / League | Private Features Org / Private Features League (unlocked, `members_private`) | 32 | 17943 |
| Org | Discovery Home / Away / Open (tournament discovery) | 30 / 31 / 32 | - |
| League | Discovery Home / Away / Open League | 30 / 31 / 32 | 17950 / 17951 / 17952 |
| Tournament | Discovery tournaments (906 has open signups, org 32) | 900-906 | - |

| User | PK | Role | Login fixture |
|------|----|------|--------------|
| kettleofketchup | 1001 | superuser | `loginAdmin()` |
| hurk_ | 1002 | staff | `loginStaff()` |
| bucketoffish55 | 1003 | regular | `loginUser()` |
| org_admin_tester | 1020 | org admin (org 1) | `loginOrgAdmin()` |
| org_staff_tester | 1021 | org staff (org 1) | `loginOrgStaff()` |
| league_admin_tester | 1030 | league admin | `loginLeagueAdmin()` |
| league_staff_tester | 1031 | league staff | `loginLeagueStaff()` |
| event_org_admin | 1080 | org admin (org 7) | `loginEventAdmin()` |
| event_player_1 | 1081 | regular | `loginEventPlayer()` |
| lobby_staff, lobby_rostered, lobby_registered, lobby_unregistered, lobby_league_staff | 7200-7204 | dota_lobby roles | `loginDotaLobby(context, role)` |
| auth_matrix_org_promoter | 1096 | promoter (org 8, Promotion locked) | `loginAuthMatrixOrgPromoter()` |
| of_owner, of_admin, of_staff, of_promoter, of_member, of_outsider, of_locked_admin, of_private_member | 7300-7307 | org features roles (orgs 30-32) | `loginOrgFeatures(context, role)` (`owner`, `admin`, `staff`, `promoter`, `member`, `outsider`, `locked_admin`, `private_member`) |
| of_player_1 .. of_player_10 | 7310-7319 | Discord-linked players of org 30's past tournaments (promotion candidates) | — |
| discovery_member | 1100 | member of org 30 only (tournament discovery) | `loginAsUser(context, 1100)` |

> **NOTE**: When this table drifts from source, read `backend/tests/data/users.py` and `backend/tests/data/organizations.py` for truth.
