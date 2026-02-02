# Organization-Scoped MMR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement organization-scoped MMR tracking with user management, claims system, and league/org membership indexing.

**Architecture:** Users can belong to multiple organizations and leagues. Tournament participants are auto-indexed to their org/league. Profile claiming allows Discord users to claim unclaimed Steam profiles within an org.

**Tech Stack:** Django REST Framework, React + TypeScript, Zustand stores, TanStack Query, Playwright E2E tests

**Branch:** `fix/ci-test-ip-whitelist` (worktree: `.worktrees/org-mmr`)

---

## Completed Tasks

### Task #28: Auto-Index Tournament Users to Org/League
**Status:** Completed

Added Django signal handler that auto-adds tournament participants to the organization and league membership when they join a tournament.

**Files Modified:**
- `backend/app/signals.py` - Tournament participant signal handler

---

### Task #29: Review useOrgStore and useLeagueStore Usage
**Status:** Completed

Reviewed Zustand store patterns for organization and league data management.

---

### Task #31: Update Tournament Detail to Use UserList
**Status:** Completed

Refactored tournament detail page to use the reusable UserList component.

---

### Task #32: Add LeagueUsers Tab
**Status:** Completed

Added Users tab to league detail page showing all indexed league members.

**Files Modified:**
- `frontend/app/routes/league.tsx` - Added UsersTab
- `frontend/app/components/league/tabs/UsersTab.tsx` - New component

---

### Task #33: Migrate Org/League Fetching to Stores
**Status:** Completed

Migrated organization and league data fetching to dedicated Zustand stores.

**Files Modified:**
- `frontend/app/stores/useOrgStore.ts`
- `frontend/app/stores/useLeagueStore.ts`

---

### Task #34: Use UserStrip in League Admin List
**Status:** Completed

Updated InfoTab to use UserStrip component for league admin display.

---

### Task #35: Move API Endpoints to Dedicated Files
**Status:** Completed

Reorganized frontend API endpoints into dedicated files for leagues and organizations.

**Files Modified:**
- `frontend/app/components/api/leagues.ts` - New file
- `frontend/app/components/api/organizations.ts` - New file

---

### Task #36: Add Search Filter to UserList
**Status:** Completed

Added search/filter functionality to the reusable UserList component.

---

### Task #37: Show Loading Indicator for User Count
**Status:** Completed

Added loading spinners for user count in tab badges.

---

### Task #38: Create Claims Page for Organization
**Status:** Completed

Created comprehensive claims management UI for organization admins.

**Files Created:**
- `frontend/app/components/organization/tabs/ClaimsTab.tsx` - Main claims tab
- `frontend/app/components/organization/tabs/ClaimCard.tsx` - Reusable claim card
- `frontend/app/components/organization/tabs/index.ts` - Module exports

**Features:**
- Status filter tabs (Pending/Approved/Rejected)
- Approve/Reject buttons with confirmation dialogs
- Rejection reason input
- Full data-testid coverage for Playwright

---

### Task #39: Test Claim Profile Flow E2E
**Status:** Completed

Added backend test endpoint for creating claim requests.

**Files Modified:**
- `backend/tests/test_auth.py` - Added `create_claim_request` endpoint
- `backend/tests/urls.py` - Added URL pattern

**Endpoint:** `POST /api/tests/create-claim-request/`
- Creates a claimer user (Discord only)
- Creates a target user (Steam only)
- Creates pending ProfileClaimRequest

---

## Pending Tasks

### Task #30: Add orgUsersCount Annotation to Backend
**Status:** Pending
**Priority:** Low (optimization)

Add annotated user count field to Organization queryset for efficient display.

**Implementation Steps:**

**Step 1:** Update OrganizationView queryset

```python
# backend/app/views/organization.py
class OrganizationView(viewsets.ModelViewSet):
    def get_queryset(self):
        return Organization.objects.annotate(
            users_count=Count('members', distinct=True)
        )
```

**Step 2:** Add field to serializer

```python
# backend/app/serializers/organization.py
class OrganizationSerializer(serializers.ModelSerializer):
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        fields = [..., 'users_count']
```

**Step 3:** Run tests

```bash
just test::run 'python manage.py test app.tests.test_organization -v 2'
```

---

### Task #40: Write Playwright Test for Admin Claims Approval
**Status:** Pending
**Priority:** High

Write E2E test verifying org admin can approve claim requests.

**Test File:** `frontend/tests/playwright/e2e/11-org-mmr/03-admin-claims.spec.ts`

**Implementation Steps:**

**Step 1:** Create test file with imports

```typescript
// frontend/tests/playwright/e2e/11-org-mmr/03-admin-claims.spec.ts
import { test, expect } from '../../fixtures';
import { API_URL } from '../../fixtures/auth';

interface ClaimRequestResponse {
  claim_id: number;
  claimer_username: string;
  target_steamid: number;
  organization_id: number;
}

// Helper to create a test claim request
async function createClaimRequest(
  context: { request: { post: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } }
): Promise<ClaimRequestResponse> {
  const response = await context.request.post(`${API_URL}/tests/create-claim-request/`);
  if (!response.ok()) {
    throw new Error('Failed to create claim request');
  }
  return (await response.json()) as ClaimRequestResponse;
}
```

**Step 2:** Write test cases

```typescript
test.describe('Admin Claims Approval', () => {
  test('org admin can approve a pending claim', async ({ page, context, loginOrgAdmin }) => {
    // Create pending claim request
    const claimData = await createClaimRequest(context);
    console.log(`Created claim ${claimData.claim_id} for org ${claimData.organization_id}`);

    // Login as org admin
    await loginOrgAdmin();

    // Navigate to organization claims tab
    await page.goto(`/organizations/${claimData.organization_id}`);
    await page.waitForLoadState('networkidle');
    await page.getByTestId('org-tab-claims').click();

    // Verify pending claim is visible
    await expect(page.getByTestId('claims-tab-pending')).toBeVisible();
    await page.waitForSelector('[data-testid="claims-list"]', { timeout: 10000 });
    await expect(page.getByTestId(`claim-card-${claimData.claim_id}`)).toBeVisible();

    // Click approve button
    await page.getByTestId(`approve-claim-btn-${claimData.claim_id}`).click();

    // Confirm in dialog
    await page.getByTestId('confirm-approve-claim').click();

    // Wait for API response and UI update
    await page.waitForTimeout(500);

    // Verify claim moved to approved tab
    await page.getByTestId('claims-tab-approved').click();
    await page.waitForSelector('[data-testid="claims-list"]', { timeout: 10000 });
    await expect(page.getByTestId(`claim-card-${claimData.claim_id}`)).toBeVisible();
  });

  test('org admin can reject a claim with reason', async ({ page, context, loginOrgAdmin }) => {
    const claimData = await createClaimRequest(context);

    await loginOrgAdmin();
    await page.goto(`/organizations/${claimData.organization_id}`);
    await page.waitForLoadState('networkidle');
    await page.getByTestId('org-tab-claims').click();

    // Wait for claims to load
    await page.waitForSelector('[data-testid="claims-list"]', { timeout: 10000 });

    // Click reject button
    await page.getByTestId(`reject-claim-btn-${claimData.claim_id}`).click();

    // Enter rejection reason
    await page.getByTestId('rejection-reason-input').fill('Profile already claimed by another user');

    // Confirm rejection
    await page.getByTestId('confirm-reject-claim').click();

    // Wait for API response
    await page.waitForTimeout(500);

    // Verify claim moved to rejected tab
    await page.getByTestId('claims-tab-rejected').click();
    await page.waitForSelector('[data-testid="claims-list"]', { timeout: 10000 });
    await expect(page.getByTestId(`claim-card-${claimData.claim_id}`)).toBeVisible();
  });
});
```

**Step 3:** Run test

```bash
just test::pw::spec 03-admin-claims
```

---

## Test Endpoints Available

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tests/login-org-admin/` | POST | Login as test org admin |
| `/api/tests/login-org-staff/` | POST | Login as test org staff |
| `/api/tests/create-claimable-user/` | POST | Create user eligible for claiming |
| `/api/tests/create-claim-request/` | POST | Create pending claim request |

---

## Frontend Data Test IDs

### Claims Tab
| Test ID | Element |
|---------|---------|
| `org-tab-claims` | Claims tab trigger |
| `claims-tab-pending` | Pending filter tab |
| `claims-tab-approved` | Approved filter tab |
| `claims-tab-rejected` | Rejected filter tab |
| `claims-list` | Claims list container |
| `claims-loading` | Loading indicator |
| `claims-empty` | Empty state message |
| `claims-error` | Error alert |

### Claim Card
| Test ID | Element |
|---------|---------|
| `claim-card-{id}` | Individual claim card |
| `approve-claim-btn-{id}` | Approve button |
| `reject-claim-btn-{id}` | Reject button |

### Confirmation Dialogs
| Test ID | Element |
|---------|---------|
| `confirm-approve-claim` | Approve confirmation button |
| `confirm-reject-claim` | Reject confirmation button |
| `rejection-reason-input` | Rejection reason text input |

---

## Running Tests

```bash
# Start test environment
just test::up

# Run all org-mmr tests
just test::pw::spec 11-org-mmr

# Run specific test
just test::pw::spec 03-admin-claims

# Run in UI mode for debugging
just test::pw::ui
```

---

## Resume Checklist

When resuming this work:

1. [ ] Verify test environment is running: `just test::ps`
2. [ ] Check test database is populated: `just test::populate::all`
3. [ ] Run existing tests to verify baseline: `just test::pw::spec 11-org-mmr`
4. [ ] Continue with Task #40 (Playwright test)
5. [ ] Optionally complete Task #30 (backend optimization)
