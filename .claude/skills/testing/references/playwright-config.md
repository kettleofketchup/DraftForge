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
baseURL: https://localhost
ignoreHTTPSErrors: true
viewport: 1280x720
trace: on-first-retry
screenshot: only-on-failure
video: off (CI) / retain-on-failure (local)
```

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
