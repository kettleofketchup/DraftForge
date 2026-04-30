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
"""

from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgUser, PositionsModel


class PartialUserPatchTests(TransactionTestCase):
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

- [ ] **Step 2: Empirical verification via the test client**

Add a temporary test to `backend/app/tests/test_user_partial_patch.py` (you'll remove it before commit):

```python
def test_global_patch_invalidates_org_user_list_cache(self):
    """When a user's nickname is edited globally, the org's users endpoint
    must reflect the change on the next GET (no stale cache)."""
    list_url = f"/api/organizations/{self.org.pk}/users/"
    # Prime the cache
    resp1 = self.client.get(list_url)
    self.assertEqual(resp1.status_code, 200)
    initial_nickname = next(
        u for u in resp1.json() if u.get("pk") == self.target.pk
    )["nickname"]
    self.assertEqual(initial_nickname, "Target")
    # Edit globally
    patch_url = f"/api/users/{self.target.pk}/"
    self.client.patch(patch_url, {"nickname": "TargetRenamed"}, format="json")
    # Second GET must reflect the change
    resp2 = self.client.get(list_url)
    after_nickname = next(
        u for u in resp2.json() if u.get("pk") == self.target.pk
    )["nickname"]
    self.assertEqual(after_nickname, "TargetRenamed")
```

```bash
just test::run 'python manage.py test app.tests.test_user_partial_patch.PartialUserPatchTests.test_global_patch_invalidates_org_user_list_cache -v 2'
```

- [ ] **Step 3: Interpret the result**

- **If the test PASSES:** cacheops auto-invalidation on `CustomUser.save()` is sufficient. Delete the temporary test (it's a one-time verification, not a permanent regression test, since cacheops behavior is library-level). Skip to Step 5.
- **If the test FAILS:** add explicit invalidation. Proceed to Step 4.

- [ ] **Step 4: (Conditional) Add explicit invalidation**

Edit `backend/app/views_main.py` `UserSerializer.update`. After `instance.save()` and after the existing post-save logic, add:

```python
from cacheops import invalidate_obj

# Invalidate downstream caches that key on related OrgUser / LeagueUser rows
for org_user in instance.orguser_set.all():
    invalidate_obj(org_user)
    invalidate_obj(org_user.organization)
for league_user in instance.leagueuser_set.all():
    invalidate_obj(league_user)
    invalidate_obj(league_user.league)
```

Re-run the verification test. Expected: PASS.

- [ ] **Step 5: Remove the temporary verification test, commit**

```bash
# Remove test_global_patch_invalidates_org_user_list_cache from test_user_partial_patch.py
git add backend/app/tests/test_user_partial_patch.py
# If Step 4 was needed:
# git add backend/app/views_main.py
git commit -m "fix(cache): invalidate org/league user lists on global user PATCH"
# If Step 4 was NOT needed (test passed on first run), there is nothing to commit; skip the commit step.
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

type DirtyMap = Partial<FieldNamesMarkedBoolean<EditUserInput>>;

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
import { ScrollArea } from '@radix-ui/react-scroll-area';
import { SCROLLAREA_CSS_SMALL } from '~/components/reusable/modal';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { ScrollBar } from '~/components/ui/scroll-area';
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

function TextField({
  form,
  fieldKey,
  label,
  type = 'text',
}: {
  form: UseFormReturn<EditUserInput>;
  fieldKey: 'nickname' | 'steam_account_id' | 'guildNickname' | 'mmr';
  label: string;
  type?: 'text' | 'number';
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
              {...field}
              type={type}
              value={field.value ?? ''}
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
  return (
    <ScrollArea className={SCROLLAREA_CSS_SMALL}>
      <div className="flex flex-col w-full gap-4">
        <TextField form={form} fieldKey="nickname" label="Nickname" />
        {showMmr && (
          <TextField form={form} fieldKey="mmr" label={mmrLabel} type="number" />
        )}
        <div className="bg-base-300 border border-border rounded-lg p-4">
          <FormLabel className="block text-center mb-3">Positions</FormLabel>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
            {POSITION_FIELDS.map(({ key, label }) => (
              <PositionSelect key={key} form={form} fieldKey={key} label={label} />
            ))}
          </div>
        </div>
        <TextField
          form={form}
          fieldKey="steam_account_id"
          label="Friend ID"
          type="number"
        />
        <TextField
          form={form}
          fieldKey="guildNickname"
          label="Discord Guild Nickname"
        />
      </div>
      <ScrollBar orientation="vertical" />
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
};
```

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

  // Re-seed when modal opens or the underlying user changes.
  // Cross-entity transitions within the same scope.kind (e.g. org A → org B)
  // are covered by the `open` toggle: the modal must close between users,
  // so the next open re-runs reset.
  useEffect(() => {
    if (open) form.reset(buildDefaults(user, scope));
  }, [open, user.pk, user.orgUserPk, scope.kind, form]);

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

Inside `PlayerModal`, alongside existing context reads:

```tsx
import React from 'react';
import { useOrgStore } from '~/store/orgStore';
import { useLeagueStore } from '~/store/leagueStore';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
// ...

// Inside the component:
const { playerModalState } = useSharedPopover();
const ctx = playerModalState.context;
const orgs = useOrgStore((s) => s.orgs);
const leagues = useLeagueStore((s) => s.leagues);

const editScope = React.useMemo<EditUserScope>(() => {
  if (ctx?.organizationId) {
    const org = orgs.find((o) => o.pk === ctx.organizationId);
    if (org) return { kind: 'org', organization: org };
  }
  if (ctx?.leagueId) {
    const league = leagues.find((l) => l.pk === ctx.leagueId);
    if (league) {
      const org = league.organization
        ? orgs.find((o) => o.pk === league.organization?.pk)
        : undefined;
      return { kind: 'league', league, organization: org };
    }
  }
  return { kind: 'global' };
}, [ctx?.organizationId, ctx?.leagueId, orgs, leagues]);
```

If `useOrgStore` / `useLeagueStore` selectors named `orgs` / `leagues` don't exist, use whatever the equivalent is in those stores (`useOrgStore.getState()` access during render is acceptable as a fallback). Verify by reading the store files first.

Then change the `<UserEditModal user={...} />` call to:

```tsx
<UserEditModal user={new User(fullUserData || displayPlayer)} scope={editScope} />
```

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

### Task 9: Add non-superuser-org-admin populate fixture + 09 scope-permissions spec

**Files:**
- Modify: `backend/tests/data/users.py` — declare a non-staff org-admin user
- Modify: `backend/tests/populate/user_edit.py` — add the user to `User Edit Org` admins
- Create: `frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts`

- [ ] **Step 1: Declare the new user in `backend/tests/data/users.py`**

Find the existing `USER_EDIT_USERS` block (around the `is_staff=False, is_superuser=False` users). Add a new module-level dataclass or dict (matching the existing pattern):

```python
ORG_ADMIN_NON_STAFF_USER = UserData(
    pk=2090,
    username="org-admin-non-staff",
    nickname="OrgAdminNonStaff",
    discord_id="2090090909",
    steam_id=None,
    is_staff=False,
    is_superuser=False,
    mmr=4000,
)
```

Use whatever fields the existing `UserData` definition requires. Verify by reading the file.

- [ ] **Step 2: Update `backend/tests/populate/user_edit.py` to seed and grant org-admin**

Add to the imports:

```python
from tests.data.users import ADMIN_USER, ORG_ADMIN_NON_STAFF_USER, USER_EDIT_USERS
```

After step 4 ("Add admin user as org admin"), add:

```python
# 4b. Create a non-superuser org admin so 09-scope-permissions.spec can verify
#     scope-aware permission gating.
oa_user, oa_created = CustomUser.objects.update_or_create(
    pk=ORG_ADMIN_NON_STAFF_USER.pk,
    defaults={
        "username": ORG_ADMIN_NON_STAFF_USER.username,
        "nickname": ORG_ADMIN_NON_STAFF_USER.nickname,
        "discordId": ORG_ADMIN_NON_STAFF_USER.discord_id,
        "is_staff": False,
        "is_superuser": False,
    },
)
if oa_created:
    oa_user.set_unusable_password()
    oa_user.save()
if oa_user not in edit_org.admins.all():
    edit_org.admins.add(oa_user)
    print(f"  Added {oa_user.username} as non-staff admin of {USER_EDIT_ORG.name}")
```

- [ ] **Step 3: Repopulate the test DB**

```bash
just db::populate::all
```

Expected output includes "Added org-admin-non-staff as non-staff admin of User Edit Org".

- [ ] **Step 4: Add a Playwright login fixture for this user (if not already present)**

Read `frontend/tests/playwright/fixtures/` to find the existing `loginAdmin` helper. Add a parallel `loginOrgAdminNonStaff` that authenticates as `org-admin-non-staff` (pk=2090). Pattern match the existing helper exactly — same auth flow, just different credentials.

- [ ] **Step 5: Write the 09 spec**

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
    targetUserPk = users.find((u: any) => u.username !== 'org-admin-non-staff').pk;
    await context.close();
  });

  test('org admin (non-superuser) sees edit button on org page', async ({
    page,
    loginOrgAdminNonStaff,
  }) => {
    await loginOrgAdminNonStaff();
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.locator('[data-testid="edit-user-btn"]')).toBeVisible();
  });

  test('org admin (non-superuser) does NOT see edit button on /users/:pk profile page', async ({
    page,
    loginOrgAdminNonStaff,
  }) => {
    await loginOrgAdminNonStaff();
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

- [ ] **Step 6: Run**

```bash
just test::pw::spec 15-edit-user/09
```

Expected: 3 tests, all green.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/data/users.py \
        backend/tests/populate/user_edit.py \
        frontend/tests/playwright/fixtures \
        frontend/tests/playwright/e2e/15-edit-user/09-scope-permissions.spec.ts
git commit -m "test(user-edit): add scope-permissions spec with non-staff org admin fixture"
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
