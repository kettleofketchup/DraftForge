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

## Fixture Index (`fixtures/index.ts`)

Re-exports all fixtures and helpers:
- Auth utilities (all login functions, types)
- HeroDraft utilities
- General helpers (`visitAndWaitForHydration`, `waitForLoadingToComplete`)
- User card helpers (`getUserCard`, `removeUser`)
- Tournament helpers (`TournamentPage` class, `navigateToTournament`)
- League helpers (`LeaguePage` class, `navigateToLeague`)

## Writing New Fixtures

1. Create `fixtures/{feature}.ts`
2. Export login/helper functions
3. If extending the test fixture, use `test.extend<YourTypes>({...})`
4. Re-export from `fixtures/index.ts`
5. Import in specs from `../../fixtures`
