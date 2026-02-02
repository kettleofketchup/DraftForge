# Authentication Test Fixtures

This document describes the test user fixtures available for Playwright E2E testing.

**If you update these fixtures, also update:**
- `backend/tests/test_auth.py` - Python test user creation functions
- `frontend/tests/playwright/fixtures/auth.ts` - Playwright login fixtures
- `frontend/tests/playwright/e2e/` - Any tests that depend on these users

## Available Login Fixtures

### Site-Level Users

| Fixture | Username | Purpose |
|---------|----------|---------|
| `loginAdmin` | `kettleofketchup` | Site superuser with Steam ID. Full admin access. |
| `loginStaff` | `hurk_` | Site staff member. Staff-level access, not superuser. |
| `loginUser` | `bucketoffish55` | Regular user. No Steam ID by default, basic access. |

### Claim Profile Testing Users

These users are specifically for testing the claim/merge profile feature.

| Fixture | Username | Has Discord | Has Steam ID | Purpose |
|---------|----------|-------------|--------------|---------|
| `loginUserClaimer` | `user_claimer` | Yes | **No** | User who can claim profiles (logs in via Discord). |
| *(test data)* | *(null)* | **No** | **Yes** | Manually-added profile (nickname: "Claimable Profile") that can be claimed. |

**How claim testing works:**

1. Org admin manually adds a player with just their Steam ID (no Discord account)
   - Has: `steamid`, `nickname`, `mmr`
   - Does NOT have: `username` (null), `discordId` (null)
   - Cannot log in - this is just a profile placeholder

2. Later, that player logs in via Discord and sees their "ghost" profile
   - The claim button shows when: target HAS steamid AND NO discordId
   - Current user must have discordId and NOT have a different steamid

3. When claimed, the backend:
   - Copies Steam ID from target to claimer
   - Updates ALL foreign key references (teams, tournaments, stats, etc.)
   - Deletes the original ghost profile

**Note:** `steamid` is unique in the database. After claiming, the claimer owns that Steam ID.

### Organization Role Users

| Fixture | Username | Role | Purpose |
|---------|----------|------|---------|
| `loginOrgAdmin` | `org_admin_tester` | Admin of org 1 | Test organization admin features. |
| `loginOrgStaff` | `org_staff_tester` | Staff of org 1 | Test organization staff features. |

### League Role Users

| Fixture | Username | Role | Purpose |
|---------|----------|------|---------|
| `loginLeagueAdmin` | `league_admin_tester` | Admin of league 1 | Test league admin features. |
| `loginLeagueStaff` | `league_staff_tester` | Staff of league 1 | Test league staff features. |

## Usage Examples

### Basic Login

```typescript
import { test, expect } from '../../fixtures';

test('admin can edit tournament', async ({ page, loginAdmin }) => {
  await loginAdmin();
  await page.goto('/tournament/1');
  // ... test admin functionality
});
```

### Organization/League Role Testing

```typescript
test('org admin can manage organization', async ({ page, loginOrgAdmin }) => {
  await loginOrgAdmin();
  await page.goto('/organizations/1');
  // ... test org admin functionality
});
```

### Claim Profile Testing

```typescript
test('user can claim profile', async ({ page, loginUserClaimer }) => {
  // This login also ensures claimable_profile exists
  await loginUserClaimer();

  await page.goto('/users');
  // claimable_profile should show claim button
  // (no Steam ID, no Discord ID)
});
```

### Login As Specific User (by PK)

```typescript
test('captain can make picks', async ({ page, loginAsUser }) => {
  await loginAsUser(42);  // Login as user with PK 42
  await page.goto('/tournament/1');
});
```

### Login By Discord ID

```typescript
test('specific captain flow', async ({ context, loginAsDiscordId }) => {
  await loginAsDiscordId(context, '584468301988757504');
  // ...
});
```

## Frontend "Login as User" Button

In dev environments, user cards display a small red login icon button that allows
quickly switching to any user's session. This is useful for debugging and manual testing.

**Location:** `frontend/app/components/user/userCard/LoginAsUserButton.tsx`

### When It Shows

The button only appears when ALL of these conditions are met:

1. **import.meta.env.DEV** - Development mode (tree-shaken from production builds)
2. **NOT running under Playwright** - Hidden during automated tests and demo recordings
3. **User has a Discord ID** - Required for the login endpoint

Uses the same pattern as react-scan in `root.tsx`.

### How It Works

1. Click the red login icon on any user card
2. Frontend calls `POST /api/tests/login-as-discord/` with the user's Discord ID
3. Page reloads with the new session

### Implementation Files

- `frontend/app/lib/test-utils.ts` - `shouldShowTestFeatures()` utility
- `frontend/app/components/user/userCard/LoginAsUserButton.tsx` - Button component
- `frontend/app/components/user/userCard.tsx` - Integration point

## Backend Test Endpoints

The login fixtures call these backend endpoints (defined in `backend/tests/test_auth.py`):

| Endpoint | Function | Description |
|----------|----------|-------------|
| `POST /api/tests/login-admin/` | `login_admin()` | Login as site admin |
| `POST /api/tests/login-staff/` | `login_staff()` | Login as site staff |
| `POST /api/tests/login-user/` | `login_user()` | Login as regular user |
| `POST /api/tests/login-user-claimer/` | `login_user_claimer()` | Login as claimer (creates claimable_profile too) |
| `POST /api/tests/login-org-admin/` | `login_org_admin()` | Login as org admin |
| `POST /api/tests/login-org-staff/` | `login_org_staff()` | Login as org staff |
| `POST /api/tests/login-league-admin/` | `login_league_admin()` | Login as league admin |
| `POST /api/tests/login-league-staff/` | `login_league_staff()` | Login as league staff |
| `POST /api/tests/login-as/` | `login_as_user()` | Login as any user by PK |
| `POST /api/tests/login-as-discord/` | `login_as_discord_id()` | Login as user by Discord ID |

## Adding New Test Users

1. **Create the user function** in `backend/tests/test_auth.py`:
   ```python
   # Reference: docs/testing/auth/fixtures.md
   def createMyTestUser() -> tuple[CustomUser, bool]:
       """Docstring describing the user."""
       assert isTestEnvironment() == True
       user, created = CustomUser.objects.update_or_create(
           username="my_test_user",
           defaults={
               "discordId": "unique_discord_id",
               "discordUsername": "my_test_user",
               "steamid": unique_steam_id,  # if needed
           }
       )
       if created:
           user.set_password("cypress")
           user.mmr = random.randint(2000, 6000)
           user.save()
       create_social_auth(user)
       return user, created
   ```

2. **Create the login endpoint** in `backend/tests/test_auth.py`:
   ```python
   @csrf_exempt
   @api_view(["POST"])
   @authentication_classes([])
   @permission_classes([AllowAny])
   def login_my_user(request):
       """Login as my test user."""
       if not isTestEnvironment(request):
           return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
       user, created = createMyTestUser()
       login(request, user, backend="django.contrib.auth.backends.ModelBackend")
       return return_tokens(user)
   ```

3. **Add URL route** in `backend/tests/urls.py`:
   ```python
   path("login-my-user/", login_my_user, name="login-my-user"),
   ```

4. **Add Playwright fixture** in `frontend/tests/playwright/fixtures/auth.ts`:
   ```typescript
   export async function loginMyUser(context: BrowserContext): Promise<void> {
     const url = `${API_URL}/tests/login-my-user/`;
     const response = await context.request.post(url);
     // ... error handling
   }

   // Add to extended test fixture
   loginMyUser: async ({ context }, use) => {
     await use(() => loginMyUser(context));
   },
   ```

5. **Export the fixture** in `frontend/tests/playwright/fixtures/index.ts`

6. **Update this documentation!**
