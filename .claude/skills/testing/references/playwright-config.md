# Playwright Config

Source: `frontend/playwright.config.ts`, `frontend/tests/playwright/global-setup.ts`

## Global Setup

`global-setup.ts` launches a browser, pre-fetches `/api/leagues/`, stores result in `process.env.PLAYWRIGHT_CACHED_LEAGUES` for test reuse.

## Test Matching

```
testDir: ./tests/playwright
testMatch: /e2e\/.*\.spec\.ts$/     (only .spec.ts files in e2e/)
testIgnore: **/fixtures/**, **/helpers/**, **/constants.ts, **/*.d.ts
```

## Projects

### 1. `chromium` - General E2E

- Runs all tests EXCEPT `/herodraft/i`
- Desktop Chrome device profile
- Supports `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` env var for Docker
- Browser args: `--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage`, `--disable-setuid-sandbox`

### 2. `herodraft` - Multi-Browser Draft

- Matches only `/herodraft.*\.spec\.ts/`
- `fullyParallel: false` (sequential - shared draft state + Redis keys)
- `dependencies: ['chromium']` (runs after chromium project)
- `headless: true` in CI/Docker, `false` locally
- `slowMo: 100ms` locally, `0ms` in CI

### `events-sequential` / `dota-lobby-sequential` - Shared-State Suites

- `events-sequential` matches `e2e/16-events/`, `dota-lobby-sequential` matches
  `e2e/18-dota-lobby/`; `chromium` ignores both directories
- `fullyParallel: false`, `dependencies: ['chromium']`
- `dota-lobby-sequential` also sets `workers: 1`: its files share one simulated
  dota_lobby and reset the same seeded games
- `just test::pw::dota-lobby` (all) / `just test::pw::cicd-dota-lobby` (@cicd).
  Specs that need the simulator skip without it; `DOTA_LOBBY_SIMULATOR_REQUIRED=1`
  makes that an error instead

### 3. `demo` - Video Recording

- `testDir: ./tests/playwright/demo`
- Matches `/.*\.demo\.ts$/`
- `headless: true`, `slowMo: 100ms`
- `fullyParallel: false`
- `timeout: 300000ms` (5 minutes)

## Parallel Execution

- `fullyParallel: true` (default, herodraft overrides to false)
- `workers: 1` default (prevents herodraft conflicts)
- Override: `--workers=2` or `PLAYWRIGHT_WORKERS=2`

## Timeouts

| Setting | Value |
|---------|-------|
| Global test timeout | 30000ms |
| Expect timeout | 10000ms |
| Action timeout | 15000ms |
| Demo timeout | 300000ms |

## Retries

- CI: 2 retries
- Local: 1 retry

## Reporters

- `html` (never auto-open)
- `list`
- `github` (CI only)

## Default Use Settings

```
baseURL: BASE_URL   # from fixtures/base-url.ts (DF_BASE_URL or docker/.env.slot)
ignoreHTTPSErrors: true
viewport: 1280x720
trace: on-first-retry
screenshot: only-on-failure
video: off (CI) / retain-on-failure (local)
```

`BASE_URL` resolves, in order: `DF_BASE_URL` (exported by `just test::pw::run` from
`python -m scripts.compose env`; `https://nginx` inside a container), this worktree's `docker/.env.slot` (checked against
the slot registry), `https://localhost` when `GITHUB_ACTIONS=true`, otherwise it throws
`No test-stack slot for this worktree. Run "just test::slot".` See
[test-stack-slots.md](test-stack-slots.md).

## CI Sharding

Tests sharded across 4 parallel runners. Run specific shard locally:

```bash
just test::pw::headless --shard=1/4
```

## Test File Organization

```
frontend/tests/playwright/
  e2e/
    01-navigation/      # Navigation tests
    02-tournament/      # Tournament tests
    ...
    14-csv-import/      # CSV import tests
    herodraft/          # HeroDraft multi-browser tests
  demo/                 # Demo recording scripts
  fixtures/             # Shared fixtures (auth, herodraft, helpers)
  helpers/              # Shared helper utilities
  global-setup.ts       # Pre-fetch leagues
```

Spec files numbered by feature for deterministic ordering. Herodraft tests in separate directory matched by herodraft project.
