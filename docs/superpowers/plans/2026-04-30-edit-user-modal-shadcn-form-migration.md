# Edit User Modal — shadcn Form Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the user-edit modal from a hand-rolled `useState` form to shadcn `Form` + react-hook-form + Zod via `<FormDialog>`, eliminate three latent "sticky-value" bugs (onFocus reset, uncontrolled Select, setForm reset race), and add a `scope` prop so the same modal works correctly in org / league / global contexts with scope-aware permissions and MMR visibility.

**Architecture:** One Zod schema + scope discriminated union drives field set, validation, permission gate, and PATCH endpoint. `<FormDialog>` provides the brand-canonical dialog shell. Inputs are `<FormField>`-driven so RHF owns reset and dirty tracking; PATCH body contains only `formState.dirtyFields`. Backend partial-PATCH semantics are pinned by Django tests added in this PR.

**Tech Stack:** React 19 + TypeScript + react-hook-form + Zod + shadcn/ui + Tailwind; Django 5 + DRF + django-cacheops; vitest (frontend unit tests for pure modules); Playwright (E2E).

**Reference spec:** `docs/superpowers/specs/2026-04-30-edit-user-modal-shadcn-form-migration-design.md`

---

## File Structure

**Backend (modify / create):**
- Create: `backend/app/tests/test_user_partial_patch.py` — pin partial-PATCH semantics for `/organizations/:org/users/:orgUser/` and `/users/:pk/`
- Verify (modify only if cache invalidation is broken): `backend/app/views_main.py` `UserSerializer.update`

**Frontend (create / modify / delete):**
- Create: `frontend/app/components/user/userCard/editUserSchema.ts` — Zod schema, `EditUserScope` types, `buildDefaults`, `pickDirty`, `dispatchPatch`, `scopeToContext`, `useScopedEditPermission`
- Create: `frontend/app/components/user/userCard/editUserSchema.test.ts` — vitest unit tests for `buildDefaults` + `pickDirty`
- Rewrite: `frontend/app/components/user/userCard/editModal.tsx` — `<FormDialog>` shell, scope-aware permission gate, inlined `onSubmit`
- Rewrite: `frontend/app/components/user/userCard/editForm.tsx` — `FormField`-driven body, controlled `<Select>`s wrapped in `<FormControl>`
- Delete: `frontend/app/components/user/userCard/handleSaveHook.tsx` — superseded by `dispatchPatch`
- Modify: `frontend/app/components/user/userCard.tsx:203` — pass `scope`
- Modify: `frontend/app/pages/tournament/hasErrors.tsx:104` — pass `scope`
- Modify: `frontend/app/components/player/PlayerModal.tsx` — read `PlayerModalContext`, derive scope, forward
- Modify: `frontend/app/components/player/PlayerPopoverTrigger.tsx`, `frontend/app/components/ui/shared-popover-renderer.tsx`, `frontend/app/components/user/userCard.tsx:43` — pass org/league context to `openPlayerModal` where appropriate

**Tests (create / modify):**
- Modify: `frontend/tests/playwright/helpers/edit-user.ts` — add `readPositionField`
- Create: `frontend/tests/playwright/e2e/15-edit-user/07-sequential-multi-user.spec.ts`
- Create: `frontend/tests/playwright/e2e/15-edit-user/08-position-persistence.spec.ts`
- Create: `frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts`
- Create: `frontend/tests/playwright/e2e/15-edit-user/10-cache-merge.spec.ts`
- Modify: `backend/tests/populate/user_edit.py` — add a non-superuser org-admin fixture for scope-permission tests
- Modify: `backend/tests/data/users.py` — declare the new fixture user

---

## Setup

### Task 0: Branch, baseline, worktree

**Files:** None modified; verification only.

- [ ] **Step 1: Create the branch from `main`**

```bash
git -C /home/kettle/git_repos/draftforge fetch origin
git -C /home/kettle/git_repos/draftforge worktree add .worktrees/edit-user-shadcn-migration -b fix/edit-user-modal-shadcn-form-migration origin/main
cd /home/kettle/git_repos/draftforge/.worktrees/edit-user-shadcn-migration
./dev
cp /home/kettle/git_repos/draftforge/backend/.env ./backend/.env
just db::migrate::all
just db::populate::all
```

Expected: worktree at `.worktrees/edit-user-shadcn-migration`, dev environment bootstrapped, all migrations applied, populate complete.

- [ ] **Step 2: Confirm spec is present**

```bash
ls -la docs/superpowers/specs/2026-04-30-edit-user-modal-shadcn-form-migration-design.md
```

Expected: file exists, ~462 lines.

- [ ] **Step 3: Run the existing edit-user Playwright suite as baseline**

```bash
just test::up
just test::pw::spec 15-edit-user
```

Expected: all 6 specs (`01-org-edit` through `06-profile-edit`) pass. Record any pre-existing failures — they are not regressions caused by this work.

- [ ] **Step 4: Run the targeted backend test path as baseline**

```bash
just test::run 'python manage.py test app.tests -v 0 --keepdb 2>&1 | tail -20'
```

Expected: green or known-flaky list documented.

---

## Backend

### Task 1: Pin partial-PATCH semantics with Django tests

**Files:**
- Create: `backend/app/tests/test_user_partial_patch.py`

**Why:** The frontend's "send only dirty fields" PATCH relies on the org and global endpoints both treating partial nested objects (e.g. `{"positions": {"carry": 1}}`) as "set carry=1, leave others alone". `update_org_user` (`admin_team.py:754-765`) already iterates `if key in positions_data`. The global `UserSerializer.update` path uses DRF's `partial=True` which propagates to nested serializers — but `PositionsSerializer` (`serializers.py:48-58`) declares all five fields without `required=False`, so this should be pinned.

- [ ] **Step 1: Write the failing tests**

Create `backend/app/tests/test_user_partial_patch.py`:

```python
"""
Tests pinning partial-PATCH semantics for both the org-scoped and global
user-update endpoints. The edit-user modal sends only dirty fields, so
both endpoints must treat partial nested 'positions' objects as
"update-only-listed-slots", not "replace-whole-positions".

We use TestCase (not TransactionTestCase) here because cacheops auto-
invalidation on post_save fires inside the test's transaction wrapper,
which is fine for these assertions. The optional cache-commit
verification test in Task 2 uses TransactionTestCase because it relies
on transaction.on_commit hooks fired by invalidate_after_commit.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgUser, PositionsModel


class PartialUserPatchTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            username="patch-admin", password="pw"
        )
        self.target_positions = PositionsModel.objects.create(
            carry=2, mid=2, offlane=2, soft_support=2, hard_support=2
        )
        self.target = CustomUser.objects.create(
            username="patch-target",
            nickname="Target",
            mmr=5000,
            steam_account_id=12345,
            positions=self.target_positions,
        )
        self.org = Organization.objects.create(name="Patch Test Org")
        self.org.admins.add(self.admin)
        self.org_user = OrgUser.objects.create(
            user=self.target, organization=self.org, mmr=5000
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_partial_positions_patch_via_org_endpoint_does_not_zero_other_slots(self):
        """PATCH {positions: {carry: 1}} must leave mid/offlane/soft_support/hard_support unchanged."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {"positions": {"carry": 1}}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target_positions.refresh_from_db()
        self.assertEqual(self.target_positions.carry, 1)
        self.assertEqual(self.target_positions.mid, 2)
        self.assertEqual(self.target_positions.offlane, 2)
        self.assertEqual(self.target_positions.soft_support, 2)
        self.assertEqual(self.target_positions.hard_support, 2)

    def test_partial_positions_patch_via_global_endpoint_passes_serializer_validation(self):
        """PATCH /users/:pk/ {positions: {carry: 3}} must return 200, not trip required-field validation."""
        url = f"/api/users/{self.target.pk}/"
        resp = self.client.patch(url, {"positions": {"carry": 3}}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target_positions.refresh_from_db()
        self.assertEqual(self.target_positions.carry, 3)
        self.assertEqual(self.target_positions.mid, 2)

    def test_org_endpoint_rejects_empty_patch(self):
        """Pin existing behavior: empty PATCH body returns 400. Frontend has a client-side guard."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_partial_mmr_patch_via_org_endpoint_does_not_clear_nickname(self):
        """PATCH {mmr: 6500} must leave nickname unchanged — proves the safety property
        the spec relies on for concurrent edits."""
        url = f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/"
        resp = self.client.patch(url, {"mmr": 6500}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.target.refresh_from_db()
        self.org_user.refresh_from_db()
        self.assertEqual(self.org_user.mmr, 6500)
        self.assertEqual(self.target.nickname, "Target")
```

- [ ] **Step 2: Run the tests**

```bash
just test::run 'python manage.py test app.tests.test_user_partial_patch -v 2'
```

Expected: 4 tests, 4 pass. If `test_partial_positions_patch_via_global_endpoint_passes_serializer_validation` fails with a 400, the fix is to add `required=False` to each field in `PositionsSerializer` (`backend/app/serializers.py:48-58`). Apply that fix in the same task.

If the empty-PATCH test reveals the endpoint actually returns 200 (contradicting the earlier review), update the spec's empty-PATCH section before continuing.

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_user_partial_patch.py
# If PositionsSerializer needed required=False:
# git add backend/app/serializers.py
git commit -m "test(users): pin partial PATCH semantics for org and global endpoints"
```

---

### Task 2: Verify and (if needed) harden cache invalidation on global PATCH

**Why:** `update_org_user` already calls `invalidate_after_commit(org_user, org, *user.tournaments, *(lu.league for lu in league_users))`. The global `UserSerializer.update` path may not trigger the same `OrgUser`-list invalidation for `@cached_as` views, which could leave org-page user lists stale until the 1-hour TTL expires when an admin edits a user's nickname/positions/steam_account_id from the profile page.

**Files:**
- Verify: `backend/app/views_main.py` (`UserSerializer.update`)
- Modify only if broken.

- [ ] **Step 1: Read the current implementation**

```bash
grep -n "class UserSerializer\|def update\|invalidate_after_commit\|invalidate_obj\|cached_as" backend/app/views_main.py | head -40
```

Note where `UserSerializer.update` ends and what it does after `instance.save()`.

- [ ] **Step 2: Read the existing invalidation logic in `UserSerializer.update`**

```bash
sed -n '1075,1115p' backend/app/serializers.py
```

The existing code already calls `invalidate_after_commit(*instance.org_memberships.all(), ...)` and same for `league_memberships`. **Note the correct reverse-manager names:**
- `OrgUser.user` declares `related_name="org_memberships"` (`backend/org/models.py:14`).
- `LeagueUser.user` declares `related_name="league_memberships"` (`backend/league/models.py:10`).

Do NOT use `instance.orguser_set` / `instance.leagueuser_set` — those reverse names do not exist and an `AttributeError` will fire at runtime.

- [ ] **Step 3: Empirical verification via a separate `TransactionTestCase`**

Append a verification class to `backend/app/tests/test_user_partial_patch.py` (this is a one-time check; the class will be removed before commit if it passes on first run):

```python
from django.test import TransactionTestCase


class GlobalPatchInvalidationVerification(TransactionTestCase):
    """One-shot check: does the global /users/:pk/ PATCH path correctly
    invalidate cached org-user-list responses? Uses TransactionTestCase
    because invalidate_after_commit fires via transaction.on_commit, which
    only runs when the outer transaction commits (TestCase wraps everything
    in a rollback-only transaction)."""

    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            username="cache-verify-admin", password="pw"
        )
        self.target = CustomUser.objects.create(
            username="cache-target", nickname="OriginalNick"
        )
        self.org = Organization.objects.create(name="Cache Verify Org")
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.target, organization=self.org, mmr=4000)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_global_patch_invalidates_org_user_list_cache(self):
        list_url = f"/api/organizations/{self.org.pk}/users/"
        resp1 = self.client.get(list_url).json()
        initial = next(u for u in resp1 if u.get("pk") == self.target.pk)["nickname"]
        self.assertEqual(initial, "OriginalNick")

        self.client.patch(
            f"/api/users/{self.target.pk}/",
            {"nickname": "RenamedNick"},
            format="json",
        )

        resp2 = self.client.get(list_url).json()
        after = next(u for u in resp2 if u.get("pk") == self.target.pk)["nickname"]
        self.assertEqual(after, "RenamedNick")
```

```bash
just test::run 'python manage.py test app.tests.test_user_partial_patch.GlobalPatchInvalidationVerification -v 2'
```

- [ ] **Step 4: Interpret the result**

- **If the test PASSES:** the existing invalidation in `UserSerializer.update` is sufficient. Delete `GlobalPatchInvalidationVerification` from the file (it's a one-time check, not a permanent regression test, since cacheops behavior is library-level). Skip to Step 6.
- **If the test FAILS:** the existing `org_memberships` / `league_memberships` invalidation is firing but missing some downstream cache key. Proceed to Step 5.

- [ ] **Step 5: (Conditional) Diagnose and patch the gap**

Re-read `UserSerializer.update` (`backend/app/serializers.py:1075-1115`) and the affected `@cached_as` views (`UserView.list` / `UserView.retrieve` at `views_main.py:190, 205`; `OrganizationView.users` at `views_main.py:1101`). Compare the cache key dependencies (`@cached_as(OrgUser, CustomUser, ...)`) against what `invalidate_after_commit` is being called with.

Most likely causes (in order of probability):
1. The view uses `keep_fresh=True` (`views_main.py:193`) which has stricter invalidation requirements.
2. The serializer doesn't include the *organization* row in the invalidation set (only the OrgUser rows).
3. A custom `_serialize_users_with_mmr` cache helper isn't keyed on `CustomUser` save.

Apply the surgical fix that resolves the gap. Example for case (2) — add the organization invalidation:

```python
# In UserSerializer.update, immediately after the existing org_memberships block:
from cacheops import invalidate_obj
# ... existing code that calls invalidate_after_commit(*instance.org_memberships.all()) ...
for org_user in instance.org_memberships.all():
    invalidate_obj(org_user.organization)  # CORRECT: reverse name is org_memberships
```

Re-run the verification test. Expected: PASS.

- [ ] **Step 6: Remove the verification class, commit**

```bash
# Remove GlobalPatchInvalidationVerification from test_user_partial_patch.py
git add backend/app/tests/test_user_partial_patch.py
# If Step 5 was needed:
# git add backend/app/serializers.py
git commit -m "fix(cache): invalidate org/league user lists on global user PATCH"
# If Step 5 was NOT needed (test passed on first run), there is nothing to commit beyond
# the cleanup of the verification class — make a small docs commit instead:
# git commit -m "test(cache): verify global PATCH invalidation already works"
```

---

## Frontend schema and helpers

### Task 3: Create `editUserSchema.ts` with vitest unit tests

**Files:**
- Create: `frontend/app/components/user/userCard/editUserSchema.ts`
- Create: `frontend/app/components/user/userCard/editUserSchema.test.ts`

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/app/components/user/userCard/editUserSchema.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import {
  buildDefaults,
  EditUserSchema,
  pickDirty,
  type EditUserInput,
  type EditUserScope,
} from './editUserSchema';

const baseUser = {
  pk: 42,
  orgUserPk: 7,
  username: 'alice',
  nickname: 'Ali',
  mmr: 5000,
  steam_account_id: 999,
  guildNickname: 'AliGuild',
  positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
  is_staff: false,
  is_superuser: false,
} as any;

const org = { pk: 11, name: 'Test Org' } as OrganizationType;
const league = { pk: 22, name: 'Test League', organization: org } as LeagueType;

describe('buildDefaults', () => {
  it('includes mmr in org scope', () => {
    const d = buildDefaults(baseUser, { kind: 'org', organization: org });
    expect(d.mmr).toBe(5000);
    expect(d.nickname).toBe('Ali');
    expect(d.positions.carry).toBe(1);
  });

  it('includes mmr in league scope', () => {
    const d = buildDefaults(baseUser, { kind: 'league', league, organization: org });
    expect(d.mmr).toBe(5000);
  });

  it('omits mmr in global scope', () => {
    const d = buildDefaults(baseUser, { kind: 'global' });
    expect('mmr' in d).toBe(false);
  });

  it('defaults missing positions to 0 not undefined', () => {
    const u = { ...baseUser, positions: { carry: 1 } };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.positions.mid).toBe(0);
    expect(d.positions.hard_support).toBe(0);
  });

  it('coerces nullish strings to null', () => {
    const u = { ...baseUser, nickname: undefined, guildNickname: null };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.nickname).toBe(null);
    expect(d.guildNickname).toBe(null);
  });
});

describe('pickDirty', () => {
  it('returns empty object when no fields are dirty', () => {
    expect(pickDirty({ nickname: 'x' } as any, {})).toEqual({});
  });

  it('picks top-level dirty fields', () => {
    expect(
      pickDirty(
        { nickname: 'NewNick', mmr: 6000 } as any,
        { nickname: true } as any,
      ),
    ).toEqual({ nickname: 'NewNick' });
  });

  it('recurses into positions for partial nested dirty', () => {
    expect(
      pickDirty(
        { positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 } } as any,
        { positions: { carry: true, hard_support: true } } as any,
      ),
    ).toEqual({ positions: { carry: 1, hard_support: 5 } });
  });

  it('combines top-level and nested dirty fields', () => {
    const data = {
      nickname: 'New',
      mmr: 6000,
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
    } as any;
    const dirty = { nickname: true, positions: { carry: true } } as any;
    expect(pickDirty(data, dirty)).toEqual({
      nickname: 'New',
      positions: { carry: 1 },
    });
  });
});

describe('EditUserSchema', () => {
  it('accepts a full valid input', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 999,
      guildNickname: 'AliGuild',
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
      mmr: 5000,
    });
    expect(result.success).toBe(true);
  });

  it('coerces numeric strings on mmr and steam_account_id', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: '999',
      guildNickname: null,
      positions: { carry: 0, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
      mmr: '5000',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.mmr).toBe(5000);
      expect(result.data.steam_account_id).toBe(999);
    }
  });

  it('rejects positions out of range', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 0,
      guildNickname: null,
      positions: { carry: 6, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    });
    expect(result.success).toBe(false);
  });
});
```

- [ ] **Step 2: Run the tests, verify they fail**

```bash
cd frontend && npx vitest run app/components/user/userCard/editUserSchema.test.ts
```

Expected: FAIL with "Failed to resolve import './editUserSchema'".

- [ ] **Step 3: Write the implementation**

Create `frontend/app/components/user/userCard/editUserSchema.ts`:

```ts
import { z } from 'zod';
import type { UseFormReturn, FieldNamesMarkedBoolean } from 'react-hook-form';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user/types';
import {
  useIsLeagueAdmin,
  useIsOrganizationStaff,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { updateOrgUser } from '~/components/api/api';
import { useUserCacheStore } from '~/store/userCacheStore';

const PositionFieldSchema = z.coerce.number().int().min(0).max(5);

export const EditUserSchema = z.object({
  nickname: z.string().trim().min(2).max(100).nullable(),
  steam_account_id: z.coerce.number().int().min(0).nullable(),
  guildNickname: z.string().trim().min(2).max(100).nullable(),
  positions: z.object({
    carry: PositionFieldSchema,
    mid: PositionFieldSchema,
    offlane: PositionFieldSchema,
    soft_support: PositionFieldSchema,
    hard_support: PositionFieldSchema,
  }),
  mmr: z.coerce.number().int().min(0).nullable().optional(),
});

export type EditUserInput = z.infer<typeof EditUserSchema>;

export type EditUserScope =
  | { kind: 'org'; organization: OrganizationType }
  | { kind: 'league'; league: LeagueType; organization?: OrganizationType }
  | { kind: 'global' };

export type EditableField = keyof EditUserInput;

export function buildDefaults(
  user: UserClassType,
  scope: EditUserScope,
): EditUserInput {
  const base = {
    nickname: user.nickname ?? null,
    steam_account_id: user.steam_account_id ?? null,
    guildNickname: user.guildNickname ?? null,
    positions: {
      carry: user.positions?.carry ?? 0,
      mid: user.positions?.mid ?? 0,
      offlane: user.positions?.offlane ?? 0,
      soft_support: user.positions?.soft_support ?? 0,
      hard_support: user.positions?.hard_support ?? 0,
    },
  } as EditUserInput;
  return scope.kind === 'global' ? base : { ...base, mmr: user.mmr ?? null };
}

type DirtyMap = Partial<Readonly<FieldNamesMarkedBoolean<EditUserInput>>>;

export function pickDirty(
  data: EditUserInput,
  dirty: DirtyMap,
): Partial<EditUserInput> {
  const out: Partial<EditUserInput> = {};
  for (const key of Object.keys(dirty) as (keyof EditUserInput)[]) {
    const flag = dirty[key];
    if (!flag) continue;
    if (key === 'positions' && typeof flag === 'object' && flag !== null) {
      const positions = data.positions;
      const nested: Partial<EditUserInput['positions']> = {};
      for (const slot of Object.keys(flag) as (keyof typeof positions)[]) {
        if ((flag as Record<string, unknown>)[slot]) {
          nested[slot] = positions[slot];
        }
      }
      out.positions = nested as EditUserInput['positions'];
    } else {
      (out as Record<string, unknown>)[key] = data[key];
    }
  }
  return out;
}

export async function dispatchPatch(
  user: UserClassType,
  scope: EditUserScope,
  payload: Partial<EditUserInput>,
): Promise<UserType> {
  if (scope.kind === 'org') {
    if (!user.orgUserPk) throw new Error('Org scope requires user.orgUserPk');
    return updateOrgUser(scope.organization.pk, user.orgUserPk, payload);
  }
  if (scope.kind === 'league') {
    // FLEXIBLE POINT: today routes through the parent org's OrgUser endpoint.
    // When a league-user PATCH endpoint lands, swap this branch.
    const orgId = scope.organization?.pk ?? scope.league.organization?.pk;
    if (!orgId || !user.orgUserPk) {
      throw new Error('League scope requires a parent org with an OrgUser link');
    }
    return updateOrgUser(orgId, user.orgUserPk, payload);
  }
  if (!user.pk) throw new Error('Global scope requires user.pk');
  return user.dbUpdate(payload);
}

export function scopeToContext(scope: EditUserScope) {
  if (scope.kind === 'org') return { orgId: scope.organization.pk };
  if (scope.kind === 'league')
    return { orgId: scope.organization?.pk ?? scope.league.organization?.pk };
  return undefined;
}

export function useScopedEditPermission(scope: EditUserScope): boolean {
  const orgStaff = useIsOrganizationStaff(
    scope.kind === 'org' ? scope.organization : null,
  );
  const leagueAdmin = useIsLeagueAdmin(
    scope.kind === 'league' ? scope.league : null,
    scope.kind === 'league' ? scope.organization : null,
  );
  const superuser = useIsSuperuser();
  if (scope.kind === 'org') return orgStaff;
  if (scope.kind === 'league') return leagueAdmin;
  return superuser;
}

// Re-exported helper for callers
export { useUserCacheStore };
```

- [ ] **Step 4: Run the tests, verify they pass**

```bash
cd frontend && npx vitest run app/components/user/userCard/editUserSchema.test.ts
```

Expected: PASS — all 11 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/user/userCard/editUserSchema.ts \
        frontend/app/components/user/userCard/editUserSchema.test.ts
git commit -m "feat(user-edit): add editUserSchema with scope types and pickDirty"
```

---

## Frontend migration core

### Task 4: Rewrite `editForm.tsx` and `editModal.tsx`, delete `handleSaveHook.tsx`, add 07-spec

**Files:**
- Rewrite: `frontend/app/components/user/userCard/editForm.tsx`
- Rewrite: `frontend/app/components/user/userCard/editModal.tsx`
- Delete: `frontend/app/components/user/userCard/handleSaveHook.tsx`
- Create: `frontend/tests/playwright/e2e/15-edit-user/07-sequential-multi-user.spec.ts`

This is the largest task. The new modal uses scope with a default of `{ kind: 'global' }` so existing callers continue to compile until updated in Tasks 5–7.

- [ ] **Step 1: Rewrite `editForm.tsx`**

Replace the entire contents of `frontend/app/components/user/userCard/editForm.tsx` with:

```tsx
import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import type { EditUserInput } from './editUserSchema';

interface Props {
  form: UseFormReturn<EditUserInput>;
  showMmr: boolean;
  mmrLabel: string;
}

const POSITION_OPTIONS: Array<[number, string]> = [
  [0, "0: Don't show this role"],
  [1, '1: Favorite'],
  [2, '2: Can play'],
  [3, '3: If the team needs'],
  [4, '4: I would rather not but I guess'],
  [5, '5: Least Favorite'],
];

type PositionKey = keyof EditUserInput['positions'];

const POSITION_FIELDS: Array<{ key: PositionKey; label: string }> = [
  { key: 'carry', label: 'Carry' },
  { key: 'mid', label: 'Mid' },
  { key: 'offlane', label: 'Offlane' },
  { key: 'soft_support', label: 'Soft Support' },
  { key: 'hard_support', label: 'Hard Support' },
];

function PositionSelect({
  form,
  fieldKey,
  label,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: PositionKey;
  label: string;
}) {
  return (
    <FormField
      control={form.control}
      name={`positions.${fieldKey}` as const}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select
            value={String(field.value)}
            onValueChange={(v) => field.onChange(parseInt(v, 10))}
          >
            <FormControl>
              <SelectTrigger data-testid={`edit-user-${fieldKey}`}>
                <SelectValue placeholder="Select" />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {POSITION_OPTIONS.map(([value, text]) => (
                <SelectItem key={value} value={String(value)}>
                  {text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function StringField({
  form,
  fieldKey,
  label,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: 'nickname' | 'guildNickname';
  label: string;
}) {
  return (
    <FormField
      control={form.control}
      name={fieldKey}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              ref={field.ref}
              name={field.name}
              onBlur={field.onBlur}
              value={field.value ?? ''}
              onChange={(e) =>
                field.onChange(e.target.value === '' ? null : e.target.value)
              }
              data-testid={`edit-user-${fieldKey}`}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function NumberField({
  form,
  fieldKey,
  label,
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: 'mmr' | 'steam_account_id';
  label: string;
}) {
  return (
    <FormField
      control={form.control}
      name={fieldKey}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              ref={field.ref}
              name={field.name}
              onBlur={field.onBlur}
              type="number"
              value={field.value ?? ''}
              onChange={(e) => {
                // Coerce to number on each keystroke so dirtyFields compares
                // numeric-to-numeric (defaultValues are numbers from buildDefaults).
                // Empty input → null (matches Zod's .nullable()).
                const raw = e.target.value;
                if (raw === '') {
                  field.onChange(null);
                } else {
                  const n = Number(raw);
                  field.onChange(Number.isFinite(n) ? n : raw);
                }
              }}
              data-testid={`edit-user-${fieldKey}`}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export const UserEditForm: React.FC<Props> = ({ form, showMmr, mmrLabel }) => {
  // No outer <ScrollArea> — FormDialog already wraps its children in one.
  return (
    <div className="flex flex-col w-full gap-4">
      <StringField form={form} fieldKey="nickname" label="Nickname" />
      {showMmr && (
        <NumberField form={form} fieldKey="mmr" label={mmrLabel} />
      )}
      <div className="bg-base-300 border border-border rounded-lg p-4">
        <h3 className="text-foreground text-center text-sm font-medium mb-3">
          Positions
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          {POSITION_FIELDS.map(({ key, label }) => (
            <PositionSelect key={key} form={form} fieldKey={key} label={label} />
          ))}
        </div>
      </div>
      <NumberField
        form={form}
        fieldKey="steam_account_id"
        label="Friend ID"
      />
      <StringField
        form={form}
        fieldKey="guildNickname"
        label="Discord Guild Nickname"
      />
    </div>
  );
};
```

**Notes on the changes (consolidated from review):**

- Section header is `<h3>`, not `<FormLabel>` — `<FormLabel>` calls `useFormField()` which requires `<FormItem>` + `<FormField>` context. Outside that context it produces broken aria.
- Outer `<ScrollArea>` removed — `FormDialog` wraps its children in a `<ScrollArea>` already (see `FormDialog.tsx:131`); nesting two scroll containers is redundant and the legacy raw `@radix-ui/react-scroll-area` `Root` (without a `Viewport`) didn't actually scroll anyway.
- `StringField` and `NumberField` are split because RHF's `dirtyFields` deep-compares to `defaultValues` — if a number input writes a string while defaults are numeric, every touch stays "dirty" until the input is cleared. The explicit numeric `onChange` keeps form state numeric end-to-end. This pattern matches `EditEventModal.tsx:331-339`.
- Position grid breakpoints: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5` covers the 1024-1279px range cleanly (3+2 instead of 2+2+1).

- [ ] **Step 2: Rewrite `editModal.tsx`**

Replace the entire contents of `frontend/app/components/user/userCard/editModal.tsx` with:

```tsx
import React, { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { UserClassType } from '~/components/user/types';
import { EditIconButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import {
  buildDefaults,
  dispatchPatch,
  EditUserSchema,
  pickDirty,
  scopeToContext,
  useScopedEditPermission,
  useUserCacheStore,
  type EditableField,
  type EditUserInput,
  type EditUserScope,
} from './editUserSchema';
import { UserEditForm } from './editForm';

interface Props {
  user: UserClassType;
  /** Defaults to global scope so legacy call sites continue compiling
   *  until they're migrated. New code should always pass an explicit scope. */
  scope?: EditUserScope;
  fields?: Partial<Record<EditableField, boolean>>;
}

export function UserEditModal({ user, scope = { kind: 'global' }, fields }: Props) {
  const canEdit = useScopedEditPermission(scope);
  const [open, setOpen] = useState(false);
  const showMmr = scope.kind !== 'global' && (fields?.mmr ?? true);

  const form = useForm<EditUserInput>({
    resolver: zodResolver(EditUserSchema),
    defaultValues: buildDefaults(user, scope),
  });

  // Re-seed when modal opens or the underlying user/scope target changes.
  // Including the entity pk (not the whole scope object literal) lets us
  // detect cross-entity transitions like org A → org B without trusting that
  // callers always close the modal between users.
  const scopeOrgPk =
    scope.kind === 'org'
      ? scope.organization.pk
      : scope.kind === 'league'
        ? (scope.organization?.pk ?? scope.league.organization?.pk ?? null)
        : null;
  const scopeLeaguePk = scope.kind === 'league' ? scope.league.pk : null;
  useEffect(() => {
    if (open) form.reset(buildDefaults(user, scope));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scope is read inline; deps cover its identity keys
  }, [open, user.pk, user.orgUserPk, scope.kind, scopeOrgPk, scopeLeaguePk, form]);

  async function onSubmit(data: EditUserInput) {
    if (!form.formState.isDirty) {
      setOpen(false);
      return;
    }
    try {
      const payload = pickDirty(data, form.formState.dirtyFields);
      const updated = await dispatchPatch(user, scope, payload);
      useUserCacheStore.getState().upsert([updated], scopeToContext(scope));
      toast.success(`${user.username} updated`);
      setOpen(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : `Failed to update ${user.username}`;
      toast.error(message);
    }
  }

  if (!canEdit) return null;

  return (
    <>
      <EditIconButton
        tooltip="Edit User"
        data-testid="edit-user-btn"
        onClick={() => setOpen(true)}
      />
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title={`Edit ${user.nickname || user.username}`}
        description="Update this user's profile."
        submitLabel="Save Changes"
        isSubmitting={form.formState.isSubmitting}
        onSubmit={form.handleSubmit(onSubmit)}
        size="md"
        data-testid="edit-user-modal"
      >
        <Form {...form}>
          <UserEditForm
            form={form}
            showMmr={showMmr}
            mmrLabel={scope.kind === 'org' ? 'Org MMR' : 'MMR'}
          />
        </Form>
      </FormDialog>
    </>
  );
}

export default UserEditModal;
```

- [ ] **Step 3: Delete `handleSaveHook.tsx`**

```bash
git rm frontend/app/components/user/userCard/handleSaveHook.tsx
```

If TypeScript reports any remaining importer of `handleSaveHook`, fix it (there should be none — the only consumer was `editModal.tsx`).

- [ ] **Step 4: Type-check the changes**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "userCard/edit|user/types|editUserSchema" | head -40
```

Expected: no errors related to the modified files. Resolve any that appear before continuing.

- [ ] **Step 5: Write the new sequential-edit Playwright spec**

Create `frontend/tests/playwright/e2e/15-edit-user/07-sequential-multi-user.spec.ts`:

```ts
/**
 * Sequential multi-user edit regression test.
 *
 * Pins the bug originally reported: editing user A then user B in succession
 * caused fields to "stick" or revert. Also pins the dirty-fields PATCH
 * behavior — only changed fields land in the request body.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  fillEditField,
  saveEditModal,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';

let orgPk: number;

test.describe('Sequential multi-user edits (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    if (!editOrg) throw new Error(`Org "${USER_EDIT_ORG_NAME}" not found. Run just db::populate::all`);
    orgPk = editOrg.pk;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd edit user A and user B sequentially; both saves persist', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();

    const userCards = page.locator('[data-testid^="usercard-"]');
    await expect(userCards.first()).toBeVisible({ timeout: 10000 });

    // Edit user A: nickname + MMR
    const cardA = userCards.nth(0);
    await openEditModal(page, cardA);
    const newNickA = `SeqA-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickA);
    await fillEditField(page, 'mmr', '6500');
    await saveEditModal(page);

    // Edit user B: nickname only
    const cardB = userCards.nth(1);
    await openEditModal(page, cardB);
    const newNickB = `SeqB-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickB);
    await saveEditModal(page);

    // Reload and verify both persist
    await page.reload();
    await page.locator('[data-testid="org-tab-users"]').click();
    await expect(page.getByText(newNickA).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(newNickB).first()).toBeVisible({ timeout: 5000 });
  });

  test('@cicd PATCH body contains only dirty fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const userCards = page.locator('[data-testid^="usercard-"]');
    await expect(userCards.first()).toBeVisible({ timeout: 10000 });

    const card = userCards.first();
    await openEditModal(page, card);

    const patchPromise = page.waitForRequest(
      (req) => req.method() === 'PATCH' && /\/users\//.test(req.url()),
      { timeout: 10000 },
    );

    const newNick = `Dirty-${Date.now()}`;
    await fillEditField(page, 'nickname', newNick);
    await saveEditModal(page);

    const patch = await patchPromise;
    const body = JSON.parse(patch.postData() || '{}');
    expect(Object.keys(body).sort()).toEqual(['nickname']);
    expect(body.nickname).toBe(newNick);
  });

  test('@cicd save with no changes does not fire a PATCH', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });

    await openEditModal(page, card);

    let patchCount = 0;
    page.on('request', (req) => {
      if (req.method() === 'PATCH' && /\/users\//.test(req.url())) patchCount++;
    });

    await page.getByRole('button', { name: 'Save Changes' }).click();
    await page.waitForTimeout(800);
    expect(patchCount).toBe(0);
  });
});
```

- [ ] **Step 6: Run the migrated suite**

```bash
just test::up
just test::pw::spec 15-edit-user
```

Expected: all specs pass (`01-org-edit` through `06-profile-edit` plus the new `07-sequential-multi-user`). If `01-06` fail, the migration broke something — debug before proceeding.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/user/userCard/editForm.tsx \
        frontend/app/components/user/userCard/editModal.tsx \
        frontend/tests/playwright/e2e/15-edit-user/07-sequential-multi-user.spec.ts
git rm frontend/app/components/user/userCard/handleSaveHook.tsx 2>/dev/null || true
git commit -m "refactor(user-edit): migrate modal to FormDialog + RHF + Zod, add sequential-edit regression test"
```

---

## Caller updates

### Task 5: Update `userCard.tsx` to pass scope

**Files:**
- Modify: `frontend/app/components/user/userCard.tsx` (around line 203)

- [ ] **Step 1: Read the current call site**

```bash
sed -n '195,215p' frontend/app/components/user/userCard.tsx
```

- [ ] **Step 2: Apply the edit**

Replace the existing `<UserEditModal user={...} />` block with a memoized scope:

```tsx
// Near the top of the component, alongside other useMemo / useStore calls:
const editScope = React.useMemo<EditUserScope>(
  () =>
    orgEntry && currentOrg
      ? { kind: 'org', organization: currentOrg }
      : { kind: 'global' },
  [orgEntry?.id, currentOrg?.pk],
);

// In the JSX where UserEditModal is rendered:
<UserEditModal
  user={
    new User(
      isUserEntry(user) && orgEntry
        ? { ...user, mmr: orgEntry.mmr, orgUserPk: orgEntry.id }
        : user,
    )
  }
  scope={editScope}
/>
```

Add the import at the top of the file:

```tsx
import type { EditUserScope } from './userCard/editUserSchema';
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep "userCard.tsx" | head -10
```

Expected: no errors.

- [ ] **Step 4: Re-run the edit-user suite**

```bash
just test::pw::spec 15-edit-user
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/user/userCard.tsx
git commit -m "feat(user-edit): pass scope from userCard"
```

---

### Task 6: Update `hasErrors.tsx` to pass league scope

**Files:**
- Modify: `frontend/app/pages/tournament/hasErrors.tsx` (around line 104)

- [ ] **Step 1: Read the current call site and surrounding context**

```bash
sed -n '1,30p' frontend/app/pages/tournament/hasErrors.tsx
sed -n '100,115p' frontend/app/pages/tournament/hasErrors.tsx
```

Determine which `league` and `organization` values are in scope. The component receives `tournament` (and via that, `league`); `organization` is available via `league.organization` or `useOrgStore`.

- [ ] **Step 2: Apply the edit**

Inside the component, before the JSX:

```tsx
import React from 'react';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';

const editScope = React.useMemo<EditUserScope>(
  () =>
    league
      ? {
          kind: 'league',
          league,
          organization: league.organization ?? undefined,
        }
      : { kind: 'global' },
  [league?.pk, league?.organization?.pk],
);
```

Replace the existing `<UserEditModal user={user} key={...} />` with:

```tsx
<UserEditModal
  user={user}
  scope={editScope}
  key={`UserEditModal-${user.pk}`}
/>
```

If `league` is not already in scope in this component, look it up via `useTournament` / `useLeague` hooks (whichever is already imported in the file). Add the necessary import.

- [ ] **Step 3: Type-check + run tests**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep "hasErrors.tsx" | head -10
just test::pw::spec 15-edit-user
```

Expected: no type errors, all specs green.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/tournament/hasErrors.tsx
git commit -m "feat(user-edit): pass league scope from tournament error panel"
```

---

### Task 7: Update `PlayerModal.tsx` and `openPlayerModal` call sites

**Files:**
- Modify: `frontend/app/components/player/PlayerModal.tsx`
- Modify: `frontend/app/components/ui/shared-popover-renderer.tsx`
- Modify: `frontend/app/components/player/PlayerPopoverTrigger.tsx`
- Modify: `frontend/app/components/user/userCard.tsx` (the `openPlayerModal` call near line 43, distinct from Task 5's edit)

- [ ] **Step 1: Read the existing context type**

```bash
sed -n '20,45p' frontend/app/components/ui/shared-popover-context.tsx
```

The existing `PlayerModalContext` has `leagueId?: number` and `organizationId?: number`. We use these to derive the scope inside `PlayerModal`.

- [ ] **Step 2: Edit `PlayerModal.tsx` to derive scope from context**

The org/league stores expose **single-entity selectors** (`currentOrg`, `currentLeague`) — there is no `orgs` array or `leagues` array. Confirm by:

```bash
grep -n "currentOrg\b\|currentLeague\b\|interface OrgState\|interface LeagueState" frontend/app/store/orgStore.ts frontend/app/store/leagueStore.ts
```

The popover context carries numeric IDs (`organizationId?`, `leagueId?`). We derive scope by matching those IDs against the singletons; if the stored entity doesn't match (e.g., user opened the modal from a different page than the one currently in the store), fall back to global scope.

Inside `PlayerModal`, alongside existing context reads:

```tsx
import React from 'react';
import { useOrgStore } from '~/store/orgStore';
import { useLeagueStore } from '~/store/leagueStore';
import { useSharedPopover } from '~/components/ui/shared-popover-context';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
// ...

// Inside the component:
const { playerModalState } = useSharedPopover();
const ctx = playerModalState.context;
const currentOrg = useOrgStore((s) => s.currentOrg);
const currentLeague = useLeagueStore((s) => s.currentLeague);

const editScope = React.useMemo<EditUserScope>(() => {
  // Org context: only trust currentOrg if its pk matches the popover's request.
  if (ctx?.organizationId && currentOrg?.pk === ctx.organizationId) {
    return { kind: 'org', organization: currentOrg };
  }
  // League context: same pk-match guard. Carry the parent organization
  // through if it's available on the league.
  if (ctx?.leagueId && currentLeague?.pk === ctx.leagueId) {
    return {
      kind: 'league',
      league: currentLeague,
      organization:
        currentOrg && currentLeague.organization?.pk === currentOrg.pk
          ? currentOrg
          : undefined,
    };
  }
  return { kind: 'global' };
}, [
  ctx?.organizationId,
  ctx?.leagueId,
  currentOrg?.pk,
  currentLeague?.pk,
  currentLeague?.organization?.pk,
  // Entity refs included so the memo recomputes if Zustand returns a new
  // object with the same pk (the returned scope embeds the entity reference,
  // and a stale closure here would feed a stale ref to FormDialog).
  currentOrg,
  currentLeague,
]);
```

Then change the `<UserEditModal user={...} />` call to:

```tsx
<UserEditModal user={new User(fullUserData || displayPlayer)} scope={editScope} />
```

**Tradeoff to be aware of:** if the popover is opened from a page whose store doesn't currently hold the relevant entity (e.g. opening a player popover from a search result that bypasses the org-page store hydration), `editScope` falls back to `global` and the edit button hides for non-superusers. This is the safe default. If a future caller needs richer behavior, extend `PlayerModalContext` to carry the full `organization` / `league` objects (the callers in Step 3 below all have access to those objects already).

- [ ] **Step 3: Update `openPlayerModal` call sites that should grant edit access**

`shared-popover-renderer.tsx:101` — when the renderer opens the modal from a popover, it currently passes no context. If the renderer has access to org/league info (check around line 90-110), pass it:

```tsx
openPlayerModal(state.player, {
  organizationId: currentOrg?.pk,
  leagueId: currentLeague?.pk,
});
```

`PlayerPopoverTrigger.tsx:31, 37` — same change. Pull org/league from store if accessible at this layer.

`userCard.tsx:43` — the userCard's own `openPlayerModal` call. Since userCard already has `currentOrg` and `orgEntry` available (from Task 5), pass `{ organizationId: currentOrg?.pk }`.

For each call site, if the surrounding component does not have org/league info available, leave the call unchanged — the modal defaults to global scope, which is the safe behavior.

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "PlayerModal|shared-popover|userCard\.tsx" | head -20
```

Expected: no errors.

- [ ] **Step 5: Smoke run**

```bash
just test::pw::spec 15-edit-user
just test::pw::spec 13-admin-team
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/player/PlayerModal.tsx \
        frontend/app/components/ui/shared-popover-renderer.tsx \
        frontend/app/components/player/PlayerPopoverTrigger.tsx \
        frontend/app/components/user/userCard.tsx
git commit -m "feat(user-edit): plumb scope through PlayerModal via PlayerModalContext"
```

---

## Test coverage expansion

### Task 8: Add `readPositionField` helper + 08 spec

**Files:**
- Modify: `frontend/tests/playwright/helpers/edit-user.ts`
- Create: `frontend/tests/playwright/e2e/15-edit-user/08-position-persistence.spec.ts`

- [ ] **Step 1: Add the helper**

Append to `frontend/tests/playwright/helpers/edit-user.ts`:

```ts
export type PositionKey = 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';

/**
 * Read the rendered text of a position SelectTrigger.
 * Used because readEditField only works for <input> elements.
 */
export async function readPositionField(page: Page, position: PositionKey): Promise<string> {
  const trigger = page.locator(`[data-testid="edit-user-${position}"]`);
  await expect(trigger).toBeVisible({ timeout: 5000 });
  return (await trigger.innerText()).trim();
}

/**
 * Set a position SelectTrigger to a specific numeric value (0-5).
 */
export async function setPositionField(
  page: Page,
  position: PositionKey,
  value: number,
): Promise<void> {
  const trigger = page.locator(`[data-testid="edit-user-${position}"]`);
  await trigger.click();
  await page.getByRole('option').filter({ hasText: new RegExp(`^${value}: `) }).click();
}
```

Re-export from the helpers' barrel (check `frontend/tests/playwright/fixtures/index.ts` for the export style and add `readPositionField` and `setPositionField` there).

- [ ] **Step 2: Write the 08 spec**

Create `frontend/tests/playwright/e2e/15-edit-user/08-position-persistence.spec.ts`:

```ts
/**
 * Position dropdown persistence regression test.
 *
 * Covers the uncontrolled-Select bug: position changes were silently
 * dropped because the legacy <Select> had no `value` prop. The new
 * controlled implementation must round-trip both visible state and
 * server payload.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  saveEditModal,
  setPositionField,
  readPositionField,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;

test.describe('Position dropdown persistence (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    orgPk = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME)?.pk;
    if (!orgPk) throw new Error('User Edit Org not found');
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd position changes persist in PATCH and re-render correctly', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });

    await openEditModal(page, card);

    const patchPromise = page.waitForRequest(
      (req) => req.method() === 'PATCH' && /\/users\//.test(req.url()),
      { timeout: 10000 },
    );

    await setPositionField(page, 'carry', 1);
    await setPositionField(page, 'hard_support', 5);
    await saveEditModal(page);

    const patch = await patchPromise;
    const body = JSON.parse(patch.postData() || '{}');
    expect(body.positions).toBeDefined();
    expect(body.positions.carry).toBe(1);
    expect(body.positions.hard_support).toBe(5);

    // Re-open and confirm the trigger displays the new selection (not placeholder)
    await openEditModal(page, page.locator('[data-testid^="usercard-"]').first());
    const carryDisplay = await readPositionField(page, 'carry');
    expect(carryDisplay).toContain('Favorite');
    const supportDisplay = await readPositionField(page, 'hard_support');
    expect(supportDisplay).toContain('Least Favorite');
  });
});
```

- [ ] **Step 3: Run**

```bash
just test::pw::spec 15-edit-user/08
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/helpers/edit-user.ts \
        frontend/tests/playwright/fixtures/index.ts \
        frontend/tests/playwright/e2e/15-edit-user/08-position-persistence.spec.ts
git commit -m "test(user-edit): add position-persistence regression spec + readPositionField helper"
```

---

### Task 9: Wire existing non-staff org admin into User Edit Org + 09 scope-permissions spec

**Files:**
- Modify: `backend/tests/populate/user_edit.py` — add existing `ORG_ADMIN_USER` (pk=1020) to `User Edit Org` admins
- Create: `frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts`

**Why:** The repo already has `ORG_ADMIN_USER` (`backend/tests/data/users.py:77`, pk=1020, no `is_staff`/`is_superuser`) and a `loginOrgAdmin` Playwright fixture (`frontend/tests/playwright/fixtures/auth.ts:289`) that hits the existing `login_org_admin` view (`backend/tests/test_auth.py:475`). We just need to make that user an admin of `User Edit Org` so the 09-spec can verify scope-aware permission gating without inventing a new user, login endpoint, or auth helper.

- [ ] **Step 1: Update `backend/tests/populate/user_edit.py` to add `ORG_ADMIN_USER` to the org admins**

Edit the imports:

```python
from tests.data.users import ADMIN_USER, ORG_ADMIN_USER, USER_EDIT_USERS
```

After step 4 ("Add admin user as org admin"), add:

```python
# 4b. Add the existing non-staff org-admin test user (pk=1020) as admin of
#     User Edit Org so 09-scope-permissions.spec can verify the scope-aware
#     permission gate (org admin can edit on org page, cannot on profile page).
org_admin_user = CustomUser.objects.filter(pk=ORG_ADMIN_USER.pk).first()
if org_admin_user and org_admin_user not in edit_org.admins.all():
    edit_org.admins.add(org_admin_user)
    print(f"  Added {org_admin_user.username} as admin of {USER_EDIT_ORG.name}")
```

`ORG_ADMIN_USER` itself is created by an earlier populate function — verify by reading `backend/tests/populate/users.py` (or wherever `populate_auth_users` lives) to confirm pk=1020 exists by the time `populate_user_edit_data` runs. If it doesn't, add an earlier-populate dependency note in the docstring; do not duplicate the user creation here.

- [ ] **Step 2: Repopulate the test DB**

```bash
just db::populate::all
```

Expected output includes "Added org_admin_tester as admin of User Edit Org".

- [ ] **Step 3: Confirm the existing Playwright login helper works**

```bash
grep -n "loginOrgAdmin\b" frontend/tests/playwright/fixtures/auth.ts | head -5
```

Expected: `loginOrgAdmin` is exported and registered as a fixture. No new helper or backend endpoint needed.

- [ ] **Step 4: Write the 09 spec**

Create `frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts`:

```ts
/**
 * Scope-aware permission gating.
 *
 * The legacy modal hard-coded `is_staff || is_superuser`, locking out
 * non-Django-staff org admins. The new scope-aware gate lets org admins
 * edit on their org page (org scope) but NOT on user profile pages
 * (global scope = superuser-only).
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;
let targetUserPk: number;

test.describe('Scope permissions (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    orgPk = editOrg.pk;
    const usersResp = await context.request.get(`${API_URL}/organizations/${orgPk}/users/`);
    const users = await usersResp.json();
    // Pick a target user that is neither the test actor (pk=1020 / org_admin_tester)
    // nor the global admin (pk=1, who has is_superuser=true and would render the
    // edit button regardless of scope, defeating the assertion).
    targetUserPk = users.find(
      (u: any) =>
        u.pk !== 1020 && u.pk !== 1 && u.username !== 'org_admin_tester'
    ).pk;
    await context.close();
  });

  test('org admin (non-superuser) sees edit button on org page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.locator('[data-testid="edit-user-btn"]')).toBeVisible();
  });

  test('org admin (non-superuser) does NOT see edit button on /users/:pk profile page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/users/${targetUserPk}`);
    await expect(page.locator('h1, [data-testid="user-profile-heading"]').first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-testid="edit-user-btn"]')).toHaveCount(0);
  });

  test('superuser on /users/:pk does NOT see MMR field in edit modal', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await visitAndWaitForHydration(page, `/users/${targetUserPk}`);
    const editBtn = page.locator('[data-testid="edit-user-btn"]');
    await expect(editBtn).toBeVisible({ timeout: 10000 });
    await editBtn.click();
    await expect(page.locator('[data-testid="edit-user-nickname"]')).toBeVisible();
    await expect(page.locator('[data-testid="edit-user-mmr"]')).toHaveCount(0);
  });
});
```

- [ ] **Step 5: Run**

```bash
just test::pw::spec 15-edit-user/09
```

Expected: 3 tests, all green.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/populate/user_edit.py \
        frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts
git commit -m "test(user-edit): add scope-permissions spec via existing org admin fixture"
```

---

### Task 10: Add 10-cache-merge spec

**Files:**
- Create: `frontend/tests/playwright/e2e/15-edit-user/10-cache-merge.spec.ts`

**Why:** The org PATCH endpoint returns `OrgUserSerializer` (slim — no `email`/`is_staff`/`discordId`). `useUserCacheStore.upsert` is supposed to merge, not replace, so prior fields survive. This spec pins that.

- [ ] **Step 1: Write the spec**

Create `frontend/tests/playwright/e2e/15-edit-user/10-cache-merge.spec.ts`:

```ts
/**
 * After an org-scoped PATCH (returns slim OrgUserSerializer payload),
 * the cached user entry must still expose `discordId`, `is_staff`,
 * `is_superuser` etc. from the prior cache state — i.e., upsert
 * merges scope-divergent payloads instead of replacing the entry.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  fillEditField,
  saveEditModal,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;
let targetUserPk: number;

test.describe('User cache merge after org PATCH (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    orgPk = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME).pk;
    const users = await (
      await context.request.get(`${API_URL}/organizations/${orgPk}/users/`)
    ).json();
    targetUserPk = users[0].pk;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd profile-page badges survive an org-scoped PATCH', async ({ page }) => {
    // Visit the profile page first to prime the cache with the FULL UserSerializer payload
    await visitAndWaitForHydration(page, `/users/${targetUserPk}`);
    const profileBadges = page.locator('[data-testid="user-profile-heading"], h1');
    await expect(profileBadges.first()).toBeVisible({ timeout: 10000 });

    // Snapshot the discord-id-bearing UI element. The exact selector depends on
    // the profile page; pick the visible username/discord display.
    const usernameLocator = page.getByText(/^[\w-]+$/).first();
    const initialUsername = await usernameLocator.innerText();

    // Now go to the org page and edit the same user (org-scoped PATCH)
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator(`[data-testid="usercard-${targetUserPk}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });
    await openEditModal(page, card);
    await fillEditField(page, 'nickname', `MergeTest-${Date.now()}`);
    await saveEditModal(page);

    // Return to the profile page. Username must still be there.
    await visitAndWaitForHydration(page, `/users/${targetUserPk}`);
    await expect(page.getByText(initialUsername).first()).toBeVisible({ timeout: 5000 });
  });
});
```

- [ ] **Step 2: Run**

```bash
just test::pw::spec 15-edit-user/10
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/15-edit-user/10-cache-merge.spec.ts
git commit -m "test(user-edit): pin cache merge after slim org-scoped PATCH"
```

---

## Final pass

### Task 11: Manual verification + full suite

**Files:** None modified.

- [ ] **Step 1: Run the full edit-user suite end-to-end**

```bash
just test::pw::spec 15-edit-user
```

Expected: 10 specs total (`01` through `10`), all green.

- [ ] **Step 2: Run adjacent suites that exercise the modal indirectly**

```bash
just test::pw::spec 13-admin-team
just test::pw::spec 12-add-user-modal
```

Expected: green (these touch user permissions and may have been affected).

- [ ] **Step 3: Run the new backend tests one more time**

```bash
just test::run 'python manage.py test app.tests.test_user_partial_patch -v 2'
```

Expected: 4 tests, all green.

- [ ] **Step 4: Manual smoke checklist on `just dev::debug`**

Open the dev environment in a browser and verify:

1. Visit an org page → click "Users" tab → click edit on a user. Modal opens with all fields populated.
2. Edit nickname only → click Save. DevTools Network tab shows PATCH body `{"nickname": "..."}` (only that field).
3. Open the modal again, click Save without changes. No PATCH request fires; modal closes.
4. Edit one position dropdown → save → reopen the modal. Trigger displays the chosen option, not "Select".
5. Visit a user profile page (`/users/:pk`) as a superuser → edit modal opens; **no MMR field is visible**.
6. Visit an org page as a non-superuser org admin → edit button appears.
7. Visit a user profile page as a non-superuser org admin → edit button is absent.
8. Modal layout matches the rest of the app — `<FormDialog>`-styled, no daisyUI residue, no `bg-gray-800` legacy panel.
9. Sequential edit: edit user A, save, reload; edit user B, save, reload; reopen user A — A's changes survived.

- [ ] **Step 5: Type-check and lint the whole frontend one more time**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json
cd frontend && npm run lint 2>/dev/null || echo "(no lint script — skip)"
```

Expected: no errors.

- [ ] **Step 6: Final commit if any small fixups were needed during smoke**

If the manual smoke surfaced a small fix (typo, missing testid, etc.):

```bash
git add <files>
git commit -m "fix(user-edit): <what you fixed>"
```

Otherwise nothing to commit — proceed to PR.

- [ ] **Step 7: Push and open PR**

```bash
git push -u origin fix/edit-user-modal-shadcn-form-migration
gh pr create --title "Migrate user-edit modal to FormDialog + RHF + Zod with scope-aware permissions" --body "$(cat <<'EOF'
## Summary

- Migrate `userCard/editModal.tsx` + `editForm.tsx` from hand-rolled `useState` form to `<FormDialog>` + react-hook-form + Zod.
- Add `EditUserScope` discriminated union (`org` / `league` / `global`) driving permission gate, MMR visibility, and PATCH endpoint.
- Send only `formState.dirtyFields` in the PATCH body; client-side guard skips empty PATCH (avoids backend 400).
- Pin partial-PATCH semantics with new Django tests.
- Add 4 new Playwright specs (`07` sequential multi-user, `08` position persistence, `09` scope permissions, `10` cache merge).

Fixes the "sticky values" admin bug (onFocus reset, uncontrolled Select, setForm reset race) and a permission gating bug that locked out non-Django-staff org admins.

Spec: `docs/superpowers/specs/2026-04-30-edit-user-modal-shadcn-form-migration-design.md`

## Test plan
- [ ] `just test::run 'python manage.py test app.tests.test_user_partial_patch -v 2'` passes
- [ ] `just test::pw::spec 15-edit-user` passes (10 specs)
- [ ] `just test::pw::spec 13-admin-team` passes
- [ ] Manual smoke per the implementation plan's Task 11 checklist
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Plan task |
|---|---|
| Modal API (scope discriminated union) | Task 3 |
| Permission resolution per scope | Task 3 (`useScopedEditPermission`) |
| MMR semantics per scope | Task 3 (`buildDefaults`) + Task 4 (`showMmr` in editModal) |
| File layout (incl. delete `handleSaveHook.tsx`) | Task 4 |
| Zod schema | Task 3 |
| Modal shell | Task 4 |
| Form body | Task 4 |
| Caller updates (userCard, hasErrors, PlayerModal) | Tasks 5, 6, 7 |
| Bug → fix mapping | Task 4 (covered by implementation) |
| Theming and visual parity (forbidden classes, grid fix) | Task 4 (new code uses tokenized classes; manual smoke verifies) |
| Display vs. submit (dirty-only PATCH, isDirty guard) | Task 4 (`onSubmit`) + Task 1 (backend test) |
| Backend response shapes / cache merge | Task 10 |
| Server-side cache invalidation | Task 2 |
| Backend partial-PATCH tests | Task 1 |
| 07 sequential multi-user | Task 4 |
| 08 position persistence | Task 8 |
| 09 scope permissions | Task 9 |
| 10 cache merge | Task 10 |
| Manual verification | Task 11 |

All sections covered.

**2. Placeholder scan:** No "TBD" / "TODO" / "fill in details" / "similar to Task N" left in the plan. Code blocks are complete.

**3. Type consistency:** `EditUserInput`, `EditUserScope`, `EditableField`, `pickDirty`, `dispatchPatch`, `scopeToContext`, `useScopedEditPermission` — names referenced consistently across Tasks 3, 4, 5, 6, 7. Function signatures match.
