# Playwright Fixtures

Source: `frontend/tests/playwright/fixtures/`

## Auth Fixture (`fixtures/auth.ts`)

### Environment

```typescript
const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
const API_URL = `https://${DOCKER_HOST}/api`;
```

### Login Functions

All login functions call backend `/api/tests/*` endpoints (TEST=true only).
They accept a `BrowserContext` and return `Promise<LoginResponse>`.

| Function | Endpoint | User |
|----------|----------|------|
| `loginAdmin(context)` | POST `/api/tests/login-admin/` | kettleofketchup (pk=1001, superuser) |
| `loginStaff(context)` | POST `/api/tests/login-staff/` | hurk_ (pk=1002, staff) |
| `loginUser(context)` | POST `/api/tests/login-user/` | bucketoffish55 (pk=1003, regular) |
| `loginUserClaimer(context)` | POST `/api/tests/login-user-claimer/` | user_claimer (pk=1011) |
| `loginOrgAdmin(context)` | POST `/api/tests/login-org-admin/` | org_admin_tester (pk=1020, DTX admin) |
| `loginOrgStaff(context)` | POST `/api/tests/login-org-staff/` | org_staff_tester (pk=1021, DTX staff) |
| `loginLeagueAdmin(context)` | POST `/api/tests/login-league-admin/` | league_admin_tester (pk=1030) |
| `loginLeagueStaff(context)` | POST `/api/tests/login-league-staff/` | league_staff_tester (pk=1031) |
| `loginAsUser(context, userPk)` | POST `/api/tests/login-as/` | Any user by PK |
| `loginAsDiscordId(context, discordId)` | POST `/api/tests/login-as-discord/` | Any user by Discord ID |

Special variant: `loginAdminFromPage(page)` uses `page.evaluate()` for native cookie handling.

### Response Type

```typescript
interface LoginResponse {
  success: boolean;
  user: { pk: number; username: string; discordUsername?: string; discordId?: string; mmr?: number; };
}
```

### Helper Functions

| Function | Purpose |
|----------|---------|
| `setSessionCookies(context, cookieHeader)` | Parse Set-Cookie header, set on context |
| `waitForHydration(page)` | Wait for React hydration to complete |
| `visitAndWait(page, url)` | Navigate + wait for hydration |

### Extended Test Fixture

Auth.ts exports a `test` fixture extending Playwright's base:
- Overrides `context` to inject `window.playwright = true` (disables react-scan in tests)
- Provides all login functions as fixtures
- Provides `waitForHydration` and `visitAndWait` as fixtures

Usage in specs:
```typescript
import { test, expect } from '../../fixtures';

test('example', async ({ context, loginAdmin, visitAndWait, page }) => {
  await loginAdmin(context);
  await visitAndWait(page, '/organizations/');
  await expect(page.getByText('DTX')).toBeVisible();
});
```

## HeroDraft Fixture (`fixtures/herodraft.ts`)

For multi-browser hero draft E2E scenarios.

### Functions

| Function | Endpoint | Purpose |
|----------|----------|---------|
| `getHeroDraftByKey(context, key)` | GET `/api/tests/herodraft-by-key/${key}/` | Get draft info by lookup key |
| `resetHeroDraft(context, draftId)` | POST `/api/tests/herodraft/${draftId}/reset/` | Reset draft to initial state |
| `createTestHeroDraft(context)` | POST `/api/tests/herodraft/create/` | Create a new test draft |

### Extended Fixture

Provides `captainA` and `captainB` (separate `BrowserContext` + `Page` per captain), `heroDraft` info object, and draft utility functions.

## Events Fixture (`fixtures/events.ts`)

For events E2E tests on the dedicated Events Test Org.

### Functions

| Function | Endpoint | Purpose |
|----------|----------|---------|
| `getEventsTestData(context)` | GET `/api/organizations/` + `/api/events/` | Look up Events Test Org and E2E Signup Event by name |
| `resetEventsData(context)` | POST `/api/tests/events/reset/` | Reset events: delete signups, delete generated events, reset E2E Signup Event |
| `triggerEventGeneration(context)` | POST `/api/tests/events/generate/` | Run `generate_upcoming_events()` synchronously (bypasses Celery beat) |
| `loginEventAdmin(context)` | POST `/api/tests/login-as/` (pk=5000) | Login as Events Test Org admin |
| `loginEventPlayer(context)` | POST `/api/tests/login-as/` (pk=5001) | Login as event player |

### Constants

| Export | Value |
|--------|-------|
| `EVENTS_ORG_NAME` | `'Events Test Org'` |
| `EVENTS_EVENT_NAME` | `'E2E Signup Event'` |

### Types

```typescript
interface EventInfo {
  pk: number;      // Event PK
  orgPk: number;   // Organization PK
  name: string;
  state: string;
}
```

### Usage Pattern for Repeater Generation Tests

```typescript
// 1. Login + reset
await resetEventsData(context);
await loginEventAdmin(context);

// 2. Create repeater via API
await context.request.post(`${API_URL}/events/repeaters/`, {
  data: { organization: 7, name: 'Test', frequency: 'daily', ... },
});

// 3. Trigger generation synchronously
await triggerEventGeneration(context);

// 4. Verify events were created
const resp = await context.request.get(`${API_URL}/events/?organization=7`);
const events = await resp.json();
```

## Fixture Index (`fixtures/index.ts`)

Re-exports all fixtures and helpers:
- Auth utilities (all login functions, types)
- HeroDraft utilities
- Events utilities (`getEventsTestData`, `resetEventsData`, `triggerEventGeneration`, `loginEventAdmin`, `loginEventPlayer`)
- General helpers (`visitAndWaitForHydration`, `waitForLoadingToComplete`)
- User card helpers (`getUserCard`, `removeUser`)
- Tournament helpers (`TournamentPage` class, `navigateToTournament`)
- League helpers (`LeaguePage` class, `navigateToLeague`)

## Locator Policy: Always Use `data-testid`

**All Playwright tests and demos MUST use `data-testid` selectors for element interaction.**

```typescript
// CORRECT — stable, decoupled from UI text
await page.locator('[data-testid="event-name-input"]').fill('Weekly Inhouse');
await page.locator('[data-testid="event-league-select"]').click();
await page.locator('[data-testid="event-league-option-7"]').click();

// WRONG — fragile, breaks when text or structure changes
await page.getByLabel('Event Name').fill('Weekly Inhouse');
await page.getByRole('combobox', { name: 'League' }).click();
await page.getByText('Events Test League').click();
```

**Exceptions (keep semantic locators):**
- `getByRole('option', { name: '...' })` — Radix `SelectItem` does NOT forward `data-testid` to the DOM, so use `getByRole('option')` for dropdown items
- `getByRole('heading')` — for asserting dialog/page titles (semantic validation)
- `getByRole('alertdialog')` — for confirmation dialogs (semantic structure)
- `getByRole('button', { name: /.../ })` — inside dialogs only (confirm/cancel buttons)

**When adding new UI components:**
1. Add `data-testid` to every interactive element (inputs, selects, buttons, checkboxes, tabs)
2. Use naming convention: `{feature}-{element}-{qualifier}` (e.g., `event-league-select`, `event-frequency-option-weekly`)
3. For dynamic list items: `{feature}-{element}-{id}` (e.g., `event-league-option-7`, `event-day-option-3`)

## CSRF Token Handling

DRF's `SessionAuthentication` enforces CSRF on POST/PATCH/DELETE requests. Use the CSRF helpers from event fixtures:

```typescript
import { postWithCsrf, patchWithCsrf } from '../../fixtures';

// Test endpoints (/api/tests/*) are @csrf_exempt — use context.request directly
await context.request.post(`${API_URL}/tests/events/reset/`);

// DRF ViewSet endpoints need CSRF
const resp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, data);
```

## Writing New Fixtures

1. Create `fixtures/{feature}.ts`
2. Export login/helper functions
3. If extending the test fixture, use `test.extend<YourTypes>({...})`
4. Re-export from `fixtures/index.ts`
5. Import in specs from `../../fixtures`
