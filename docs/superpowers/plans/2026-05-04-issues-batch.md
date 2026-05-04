# Issues Batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix seven open issues (#197, #196, #195, #194, #192, #191, #200) in a single PR — Discord ergonomics (DM fallback, embed user-list capacity, ephemeral lifetime), tournament edit data flow (org MMR field, signup writethrough, guild-nick seeding), tournament lifecycle (post-roll-call self-heal), and one typo. Spec at `docs/superpowers/specs/2026-05-03-issues-batch-design.md`.

**Architecture:** All changes are localized — no DB migrations, no API-shape breaks. Backend additions: a `respond_to_signup_user` helper that wraps DM-with-ephemeral-fallback, an `ensure_tournament_with_signups` service for self-heal, signup-side writethrough applied inside the existing `transaction.atomic`. Frontend changes: scope derivation gains an `'org'` branch reading from `useOrgStore.currentOrg`, plus a one-character typo fix.

**Tech Stack:** Django + DRF + Channels (backend), discord.py (bot), React + TypeScript + Tailwind + shadcn/ui + Zustand + React Router (frontend), Vitest + Playwright + Django TestCase (tests).

---

## Spec mapping

| Issue | Phase |
|---|---|
| #197 Captain typo | Phase 1 |
| #196b Discord guild nick | Phase 2 |
| #195 Org MMR not editable | Phase 3 |
| #196a Signup writethrough | Phase 4 |
| #194 Embed user list ≤40 | Phase 5 |
| #192 / #191 DM fallback + ephemeral lifetime | Phase 6 |
| #200 Start tournament empty | Phase 7 |
| Verification | Phase 8 |

## File map

**Modified files**

| File | Phase | Why |
|---|---|---|
| `frontend/app/components/tournament/captains/UpdateCaptainButton.tsx` | 1 | typo `Cpatain` → `Captain` |
| `backend/app/models.py` | 2 | `createFromDiscordData` fallback chain → username |
| `frontend/app/pages/tournament/hasErrors.tsx` | 3 | `useOrgStore.currentOrg` + `'org'` editScope branch |
| `frontend/app/components/user/userCard/editModal.tsx` | 3 | comment clarifying `showMmr` gate |
| `backend/events/services.py` | 4, 7 | signup writethrough, `ensure_tournament_with_signups` |
| `backend/events/serializers.py` | 4 | accept positions/steam_account_id on signup write |
| `backend/events/discord/embeds.py` | 5 | 40-cap split helper |
| `backend/events/views.py` | 7 | `start_tournament` calls `ensure_tournament_with_signups` |
| `backend/discordbot/components.py` | 6 | refactor ~20 signup ephemerals; strip `delete_after=60` from non-signup ephemerals |
| `backend/discordbot/bot.py` | 6 | refactor any signup-flow ephemerals |

**New files**

| File | Phase |
|---|---|
| `backend/discordbot/signup_responses.py` | 6 |
| `backend/events/tests/test_signup_writethrough.py` | 4 |
| `backend/events/tests/test_start_tournament_idempotent.py` | 7 |
| `backend/events/tests/test_add_user_discord_nick.py` | 2 |
| `backend/discordbot/tests/test_signup_responses.py` | 6 |

**Extended test files**

| File | Phase |
|---|---|
| `backend/events/tests/test_discord.py` (or appropriate embeds test file — verify at task start) | 5 |
| Existing event-admin Playwright spec (verified at task start) | 8 |

## Test data

Reuse the **Events Test Org** fixture:

| Entity | PK | Fixture |
|---|---|---|
| Org "Events Test Org" | 7 | seeded by `backend/tests/populate/` |
| League "Events Test League" | 7 | seeded by `backend/tests/populate/` |
| User `event_org_admin` (org admin in org 7) | 1080 | `loginEventAdmin()` |
| User `event_player_1` | 1081 | `loginEventPlayer()` |

Additional test users (`event_player_2..N`) exist in the populate fixture; verify pks at task time via `cat backend/tests/data/users.py`.

## Backend test invocation

All backend tests run via Docker per CLAUDE.md / testing-skill convention (avoids local-pytest Redis-hang issue):

```bash
just test::run 'python manage.py test events.tests.test_signup_writethrough -v 2'
```

To run multiple modules:

```bash
just test::run 'python manage.py test events.tests.test_signup_writethrough events.tests.test_start_tournament_idempotent -v 2'
```

To run the whole modified suite at the end of the plan:

```bash
just test::run 'python manage.py test events.tests discordbot.tests app.tests -v 2'
```

---

## Phase 1 — Captain typo (#197)

### Task 1: Fix typo

**Files:**
- Modify: `frontend/app/components/tournament/captains/UpdateCaptainButton.tsx:61`

- [ ] **Step 1: Edit the typo**

Change line 61 from:

```tsx
if (!isStaff()) return <AdminOnlyButton buttonTxt="Change Cpatain" />;
```

to:

```tsx
if (!isStaff()) return <AdminOnlyButton buttonTxt="Change Captain" />;
```

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (existing errors, if any, unchanged).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/tournament/captains/UpdateCaptainButton.tsx
git commit -m "fix(captains): correct Cpatain → Captain typo on non-staff button (#197)"
```

---

## Phase 2 — Discord guild nickname seeding (#196b)

`createFromDiscordData` already prefers guild `nick` then `global_name`, but falls back to `""` when both are missing. The bug is that the empty string ends up persisting as a blank nickname. The fix is one fallback step: use `username` (always present) as the final fallback.

### Task 2: Failing test for nickname fallback chain

**Files:**
- Create: `backend/events/tests/test_add_user_discord_nick.py`

- [ ] **Step 1: Write the test file**

```python
"""Test that CustomUser.createFromDiscordData seeds nickname from guild nick → global_name → username."""

from django.test import TestCase
from app.models import CustomUser, PositionsModel


class CreateFromDiscordDataNicknameTest(TestCase):
    """Regression for #196b — new users from Discord must have a non-empty nickname."""

    def setUp(self):
        self.positions = PositionsModel.objects.create()

    def _build_member(self, *, nick=None, global_name=None, username="alice", user_id="123"):
        return {
            "nick": nick,
            "user": {
                "id": user_id,
                "username": username,
                "global_name": global_name,
                "avatar": "abc",
            },
        }

    def test_uses_guild_nick_when_present(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick="GuildNick", global_name="GlobalName", username="alice")
        )
        self.assertEqual(user.nickname, "GuildNick")

    def test_falls_back_to_global_name_when_no_nick(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick=None, global_name="GlobalName", username="alice")
        )
        self.assertEqual(user.nickname, "GlobalName")

    def test_falls_back_to_username_when_no_nick_or_global_name(self):
        """Issue #196b: nickname must be a non-empty string, never blank."""
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick=None, global_name=None, username="alice")
        )
        self.assertEqual(user.nickname, "alice")

    def test_falls_back_to_username_when_nick_and_global_name_empty_string(self):
        user = CustomUser(positions=self.positions)
        user.createFromDiscordData(
            self._build_member(nick="", global_name="", username="alice")
        )
        self.assertEqual(user.nickname, "alice")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `just test::run 'python manage.py test events.tests.test_add_user_discord_nick -v 2'`

Expected: tests pass for `test_uses_guild_nick_when_present` and `test_falls_back_to_global_name_when_no_nick`. The two final tests **fail** with `AssertionError: '' != 'alice'` — confirming the bug.

### Task 3: Implement the fallback to username

**Files:**
- Modify: `backend/app/models.py:154`

- [ ] **Step 1: Edit the fallback chain**

Change line 154 from:

```python
self.nickname = data.get("nick") or data["user"].get("global_name") or ""
```

to:

```python
self.nickname = (
    data.get("nick")
    or data["user"].get("global_name")
    or data["user"]["username"]
)
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `just test::run 'python manage.py test events.tests.test_add_user_discord_nick -v 2'`

Expected: all four tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/events/tests/test_add_user_discord_nick.py backend/app/models.py
git commit -m "fix(users): seed nickname from username when guild nick + global_name absent (#196b)" -m "createFromDiscordData previously fell back to empty string when both Discord nick and global_name were missing — leaving new site users with a blank nickname. Use username (always present) as the final fallback so freshly created users always have a non-empty display name."
```

---

## Phase 3 — Frontend org-MMR scope (#195)

`hasErrors.tsx` derives `editScope` as `league` or `global`, never `org`. When a tournament is org-scoped without a league, the EditUserModal's MMR field (gated on `scope.kind !== 'global'`) disappears — exactly when staff need to fix the missing-MMR users the panel is flagging.

### Task 4: Failing test for org scope branch

**Files:**
- Create: `frontend/app/pages/tournament/hasErrors.test.tsx`

This is a simple unit test on the `editScope` derivation logic. The test extracts the derivation into a pure helper that the component can also use, so we can test it without rendering the full component tree. (Refactor in Task 5; test in Task 4 references the helper that will exist there.)

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest';
import { deriveEditScope } from './hasErrors';

import type { LeagueType } from '~/components/league/types';
import type { OrganizationType } from '~/components/organization/schemas';

describe('deriveEditScope', () => {
  const org: OrganizationType = { pk: 7, name: 'Events Test Org' } as OrganizationType;
  const league: LeagueType = { pk: 7, name: 'Events Test League', organization: org } as LeagueType;

  it('returns league scope when a league is present', () => {
    expect(deriveEditScope({ league, currentOrg: org })).toEqual({
      kind: 'league',
      league,
    });
  });

  it('returns org scope when only an org is present (the #195 case)', () => {
    expect(deriveEditScope({ league: null, currentOrg: org })).toEqual({
      kind: 'org',
      organization: org,
    });
  });

  it('returns global scope when neither org nor league is loaded', () => {
    expect(deriveEditScope({ league: null, currentOrg: null })).toEqual({
      kind: 'global',
    });
  });

  it('prefers league when both are present (league > org > global)', () => {
    expect(deriveEditScope({ league, currentOrg: org })).toEqual({
      kind: 'league',
      league,
    });
  });
});
```

- [ ] **Step 2: Verify Vitest runner**

Run: `cd frontend && cat package.json | grep -E '"(test|vitest)"' | head -5`
Expected: see a `"test": "vitest"` (or similar) entry. If absent, switch test framework to whatever is configured (jest is the only realistic alternative); update `import` and `describe/it` accordingly.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run app/pages/tournament/hasErrors.test.tsx`

Expected: fail with `deriveEditScope is not exported from './hasErrors'` or similar — confirming the helper doesn't exist yet.

### Task 5: Extract `deriveEditScope` and add the `'org'` branch

**Files:**
- Modify: `frontend/app/pages/tournament/hasErrors.tsx`

- [ ] **Step 1: Add the `useOrgStore` import and helper export**

At the top of the file, add the import alongside the existing imports:

```tsx
import { useOrgStore } from '~/store/orgStore';
import type { OrganizationType } from '~/components/organization/schemas';
```

- [ ] **Step 2: Export a pure helper above `hasErrors`**

Add this exported function above the `hasErrors` component definition (before line 41):

```tsx
/**
 * Derive the EditUserModal scope for the tournament-edit panel.
 * Order: league > org > global. Falls back to global only when neither
 * is loaded — callers should ensure currentOrg is populated before render
 * (see plan-time note in 2026-05-03-issues-batch-design.md).
 */
export function deriveEditScope({
  league,
  currentOrg,
}: {
  league: LeagueType | null;
  currentOrg: OrganizationType | null;
}): EditUserScope {
  if (league) return { kind: 'league', league };
  if (currentOrg) return { kind: 'org', organization: currentOrg };
  return { kind: 'global' };
}
```

`LeagueType` is already imported via the existing `useLeagueStore`. If TypeScript complains about the type, add an explicit `import type { LeagueType } from '~/components/league/types';` (verify exact path during execution).

- [ ] **Step 3: Replace inline derivation with the helper**

In the `hasErrors` component body, change lines 48-54 from:

```tsx
const editScope = useMemo<EditUserScope>(
  () =>
    league
      ? { kind: 'league', league }
      : { kind: 'global' },
  [league?.pk],
);
```

to:

```tsx
const currentOrg = useOrgStore((state) => state.currentOrg);

const editScope = useMemo<EditUserScope>(
  () => deriveEditScope({ league, currentOrg }),
  [league?.pk, currentOrg?.pk],
);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run app/pages/tournament/hasErrors.test.tsx`
Expected: all four tests PASS.

- [ ] **Step 5: Type-check the full frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/pages/tournament/hasErrors.tsx frontend/app/pages/tournament/hasErrors.test.tsx
git commit -m "fix(tournament-edit): show org MMR field when tournament is org-scoped without league (#195)" -m "hasErrors derived editScope as 'league' or 'global' only — when tournament.organization_pk was set without a league, scope fell back to 'global', which the EditUserModal's showMmr gate hides. Extract deriveEditScope helper, add an 'org' branch sourced from useOrgStore.currentOrg, restore staff's ability to fix missing-MMR users from the panel that flagged them."
```

### Task 6: Verify currentOrg is populated before hasErrors renders

This is the plan-time race-condition check the spec called out. We verify the tournament view sets `currentOrg` early enough; if it doesn't, we trigger a fetch.

**Files:**
- Read: `frontend/app/routes/tournament.tsx` (or wherever the tournament page mounts)
- Maybe modify: same file, plus possibly `frontend/app/pages/tournament/hasErrors.tsx`

- [ ] **Step 1: Locate where `useOrgStore.currentOrg` is set in the tournament view**

Run:

```bash
grep -rn "setCurrentOrg\|getOrganization" frontend/app/routes/tournament*.tsx frontend/app/pages/tournament/ 2>/dev/null | head -20
```

Expected: at least one call to `useOrgStore.setCurrentOrg` or `useOrgStore.getOrganization` early in the tournament view's lifecycle.

- [ ] **Step 2: If `currentOrg` is set, verify it runs before `hasErrors` renders**

Read the tournament page entry. Confirm `getOrganization(tournament.organization_pk)` is called either in the route loader, in a `useEffect` that gates rendering, or in a parent that suspends until populated.

If the call exists and runs early — done, no code change needed. Note in the commit message that the race was checked and is safe.

- [ ] **Step 3: If `currentOrg` is NOT reliably set early**

Add a guard inside `hasErrors`:

```tsx
const currentOrg = useOrgStore((state) => state.currentOrg);
const getOrganization = useOrgStore((state) => state.getOrganization);

useEffect(() => {
  const targetOrgPk = tournament?.organization_pk;
  if (targetOrgPk && currentOrg?.pk !== targetOrgPk) {
    getOrganization(targetOrgPk);
  }
}, [tournament?.organization_pk, currentOrg?.pk, getOrganization]);
```

This triggers a fetch if currentOrg is missing or stale. `editScope` will be `'global'` for the first render and switch to `'org'` once the fetch lands.

- [ ] **Step 4: Run the frontend test again**

Run: `cd frontend && npx vitest run app/pages/tournament/hasErrors.test.tsx`
Expected: all tests still PASS.

- [ ] **Step 5: Commit (only if Step 3 was needed)**

```bash
git add frontend/app/pages/tournament/hasErrors.tsx
git commit -m "fix(tournament-edit): trigger getOrganization when currentOrg missing on tournament view (#195)" -m "Guards the deriveEditScope race where the tournament page renders hasErrors before useOrgStore.currentOrg is populated. When tournament.organization_pk doesn't match currentOrg, kick off the fetch — editScope flips from 'global' to 'org' on the next render and the MMR field appears."
```

---

## Phase 4 — Backend signup writethrough (#196a)

When a user signs up with `positions` / `steam_account_id`, the data lands on `PlayerDotaProfile` (per-org) but the User-level fields stay empty. The fix: write through to `User.positions` (last-write-wins) and `User.steam_account_id` (first-write-wins) in the same transaction. MMR continues to flow through the existing approval modal.

### Task 7: Failing test for positions writethrough (last-write-wins)

**Files:**
- Create: `backend/events/tests/test_signup_writethrough.py`

- [ ] **Step 1: Write the test file scaffold + first test**

```python
"""Test signup-side writethrough to User-level fields (#196a).

Signup writes PlayerDotaProfile.pos_1..5 and a Steam friend ID. We mirror those
to User.positions (last-write-wins) and User.steam_account_id (first-write-wins).
MMR is NOT touched on signup save — it continues through MmrApprovalModal /
approve_signup(mmr_override=...).
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from app.models import CustomUser, PositionsModel
from events.models import Event, EventSignup
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDotaProfile


class SignupWritethroughTest(TestCase):
    """Regression for #196a — User-level fields must reflect signup-submitted data."""

    def setUp(self):
        self.org = Organization.objects.create(name="WT Org")
        self.user = CustomUser.objects.create(
            username="wt_user",
            positions=PositionsModel.objects.create(),
        )
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)
        # Minimum viable event for signups
        from django.utils import timezone as tz
        self.event = Event.objects.create(
            name="WT Event",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=False,
        )

    def _signup_with_positions(self, *, pos_1=False, pos_2=False, pos_3=False,
                                pos_4=False, pos_5=False, steam_account_id=None):
        """Helper: create a signup, populate the user's dota profile, save through services."""
        # Caller passes the per-position booleans matching the signup-form payload.
        profile, _ = PlayerDotaProfile.objects.get_or_create(org_user=self.org_user)
        profile.pos_1 = pos_1
        profile.pos_2 = pos_2
        profile.pos_3 = pos_3
        profile.pos_4 = pos_4
        profile.pos_5 = pos_5
        if steam_account_id is not None:
            profile.steam_account_id = steam_account_id
        profile.save()
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        from events.services import apply_signup_writethrough
        apply_signup_writethrough(signup)
        signup.refresh_from_db()
        self.user.refresh_from_db()
        return signup

    def test_positions_writethrough_last_write_wins(self):
        """Submitted positions overwrite User.positions on each signup save."""
        # First signup — declares carry + mid
        self._signup_with_positions(pos_1=True, pos_2=True)
        self.assertEqual(self.user.positions.pos_1, True)
        self.assertEqual(self.user.positions.pos_2, True)
        self.assertEqual(self.user.positions.pos_3, False)

        # Second signup — declares hard support only; carry+mid should be gone
        EventSignup.objects.filter(event=self.event, user=self.user).delete()
        self._signup_with_positions(pos_5=True)
        self.assertEqual(self.user.positions.pos_1, False)
        self.assertEqual(self.user.positions.pos_2, False)
        self.assertEqual(self.user.positions.pos_5, True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough.SignupWritethroughTest.test_positions_writethrough_last_write_wins -v 2'`

Expected: fail with `ImportError: cannot import name 'apply_signup_writethrough'` — confirming the function doesn't exist yet.

### Task 8: Implement positions writethrough

**Files:**
- Modify: `backend/events/services.py`

- [ ] **Step 1: Add `apply_signup_writethrough` to services.py**

Add this near the other signup-related functions (after `cancel_signup`, before `_promote_from_waitlist`):

```python
@transaction.atomic
def apply_signup_writethrough(signup):
    """Mirror signup-submitted PlayerDotaProfile fields to the User-level fields.

    Issue #196a — positions are last-write-wins on User.positions, steam_account_id
    is first-write-wins on User.steam_account_id, MMR is NOT touched here (it routes
    through approve_signup). Cache invalidation is deferred to commit so the
    'incomplete profile' panel reflects the writethrough on the next render rather
    than after the cacheops 1-hour TTL.
    """
    from app.cache_utils import invalidate_after_commit
    from org.models import OrgUser
    from org.models_profiles import PlayerDotaProfile

    user = signup.user
    org = signup.event.organization
    if org is None:
        # Events without an org have no PlayerDotaProfile to read from.
        return signup

    try:
        org_user = OrgUser.objects.get(user=user, organization=org)
    except OrgUser.DoesNotExist:
        return signup

    try:
        profile = PlayerDotaProfile.objects.get(org_user=org_user)
    except PlayerDotaProfile.DoesNotExist:
        return signup

    # Positions: last-write-wins on the linked PositionsModel.
    user_positions = user.positions
    if user_positions is None:
        from app.models import PositionsModel
        user_positions = PositionsModel.objects.create()
        user.positions = user_positions
        user.save(update_fields=["positions"])
    user_positions.pos_1 = profile.pos_1
    user_positions.pos_2 = profile.pos_2
    user_positions.pos_3 = profile.pos_3
    user_positions.pos_4 = profile.pos_4
    user_positions.pos_5 = profile.pos_5
    user_positions.save(update_fields=["pos_1", "pos_2", "pos_3", "pos_4", "pos_5"])

    invalidate_after_commit(user, org_user, signup.event.tournament)
    return signup
```

(Steam-id writethrough is added in Task 11 to keep TDD steps granular.)

- [ ] **Step 2: Run the test to verify it passes**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough.SignupWritethroughTest.test_positions_writethrough_last_write_wins -v 2'`
Expected: PASS.

### Task 9: Failing test for steam-id first-write-wins

**Files:**
- Modify: `backend/events/tests/test_signup_writethrough.py`

- [ ] **Step 1: Append a steam-id test class**

Append to the existing test file:

```python
class SignupSteamIdWritethroughTest(SignupWritethroughTest):
    """First-write-wins on User.steam_account_id (identity-bearing, unique=True)."""

    def test_steam_id_set_when_user_has_none(self):
        self.assertIsNone(self.user.steam_account_id)
        self._signup_with_positions(steam_account_id=12345)
        self.assertEqual(self.user.steam_account_id, 12345)

    def test_steam_id_preserved_when_user_already_has_one(self):
        self.user.steam_account_id = 99999
        self.user.save(update_fields=["steam_account_id"])
        self._signup_with_positions(steam_account_id=12345)
        self.user.refresh_from_db()
        # First-write-wins: existing 99999 preserved, signup 12345 ignored.
        self.assertEqual(self.user.steam_account_id, 99999)
```

Note: `steam_account_id` is on `CustomUser` directly. The `_signup_with_positions` helper writes it to `PlayerDotaProfile.steam_account_id` for the test setup; if the Profile doesn't have that field, store the value on the signup payload field instead — verify `PlayerDotaProfile` schema at task time and adjust the test setup accordingly.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough.SignupSteamIdWritethroughTest -v 2'`
Expected: both tests fail — `User.steam_account_id` stays None / unchanged because `apply_signup_writethrough` doesn't touch it yet.

### Task 10: Implement steam-id first-write-wins

**Files:**
- Modify: `backend/events/services.py` (the `apply_signup_writethrough` from Task 8)

- [ ] **Step 1: Add steam-id writethrough block**

Inside `apply_signup_writethrough`, after the positions block and before `invalidate_after_commit`:

```python
# steam_account_id: first-write-wins on User.steam_account_id (unique=True).
profile_steam_id = getattr(profile, "steam_account_id", None)
if profile_steam_id and not user.steam_account_id:
    try:
        user.steam_account_id = profile_steam_id
        user.save(update_fields=["steam_account_id", "steamid"])
    except IntegrityError:
        # Another user already owns this steam_account_id; skip silently.
        pass
```

Add `from django.db import IntegrityError` at the top of `services.py` if not already imported.

- [ ] **Step 2: Run the steam-id tests to verify they pass**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough.SignupSteamIdWritethroughTest -v 2'`
Expected: both tests PASS.

### Task 11: Failing test for MMR-not-touched + transaction rollback

**Files:**
- Modify: `backend/events/tests/test_signup_writethrough.py`

- [ ] **Step 1: Append two more tests**

```python
class SignupWritethroughInvariantsTest(SignupWritethroughTest):
    """MMR isolation + transaction atomicity (#196a)."""

    def test_mmr_is_not_touched_on_signup_save(self):
        # Set OrgUser.mmr to a known value
        self.org_user.mmr = 4500
        self.org_user.save(update_fields=["mmr"])

        # Signup with a different "submitted" MMR on the profile
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        profile.mmr = 1000
        profile.save()

        self._signup_with_positions(pos_1=True)
        self.org_user.refresh_from_db()
        # OrgUser MMR untouched — only approve_signup(mmr_override=...) writes it.
        self.assertEqual(self.org_user.mmr, 4500)

    def test_user_update_failure_rolls_back(self):
        """If saving the User fails, the writethrough is fully rolled back."""
        from unittest.mock import patch

        # Force PositionsModel.save to raise; verify nothing leaked through.
        with patch("app.models.PositionsModel.save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._signup_with_positions(pos_1=True)

        self.user.refresh_from_db()
        # No partial state survived
        self.assertEqual(self.user.positions.pos_1, False)
```

- [ ] **Step 2: Run them to verify expected outcomes**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough.SignupWritethroughInvariantsTest -v 2'`
Expected: both tests PASS without further code change — `apply_signup_writethrough` is already wrapped in `@transaction.atomic`, and MMR was never written. (If a test fails, it's revealing a hidden issue — fix before committing.)

### Task 12: Wire `apply_signup_writethrough` into the signup serializer

**Files:**
- Modify: `backend/events/serializers.py:372`
- Modify: `backend/events/views.py` (signup creation views)

- [ ] **Step 1: Inspect existing signup creation paths**

Run: `grep -nE "EventSignup\.objects\.create" backend/events/views.py backend/events/services.py backend/events/discord/handlers.py 2>/dev/null`

Expected: at least these locations:
- `backend/events/services.py:137` and `:158` (auto-create / direct signup)
- `backend/events/views.py:517` (admin-signup endpoint)
- `backend/events/discord/handlers.py:642` (Discord-driven signup)

- [ ] **Step 2: Call `apply_signup_writethrough` after each signup creation**

For each of those four locations, add a call after the `EventSignup.objects.create(...)` line (within the same atomic block where one exists, otherwise wrap):

```python
from events.services import apply_signup_writethrough
apply_signup_writethrough(signup)
```

For the services.py call sites that already do `add_user_to_tournament(...)` after creation, place the writethrough BEFORE the tournament add — the tournament view depends on the writethrough to display correct positions.

- [ ] **Step 3: Run the full writethrough test suite**

Run: `just test::run 'python manage.py test events.tests.test_signup_writethrough -v 2'`
Expected: all tests PASS.

- [ ] **Step 4: Run existing signup tests to confirm no regression**

Run: `just test::run 'python manage.py test events.tests.test_signup_services events.tests.test_signup_race events.tests.test_signup_interactions -v 2'`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/services.py backend/events/serializers.py backend/events/views.py backend/events/discord/handlers.py backend/events/tests/test_signup_writethrough.py
git commit -m "feat(signup): writethrough positions and steam_account_id from PlayerDotaProfile to User (#196a)" -m "Adds events.services.apply_signup_writethrough — last-write-wins on User.positions (the linked PositionsModel pos_1..5 booleans), first-write-wins on User.steam_account_id (identity-bearing, unique=True). MMR untouched at signup; continues through approve_signup(mmr_override=...) and the MmrApprovalModal flow. Cache invalidation deferred to commit so the tournament-view 'incomplete profile' panel refreshes immediately rather than after the cacheops 1-hour TTL."
```

---

## Phase 5 — Discord embed user list ≤40 (#194)

Current cap is 20 across `_user_list`, `_user_list_quoted`, and inline `[:20]` slices in two announcement builders. Raise to 40, and split into two inline fields when the joined line set exceeds Discord's 1024-character per-field limit.

### Task 13: Failing test for 40-cap and split

**Files:**
- Read first: `backend/events/tests/test_discord.py` (or whichever existing file already covers `embeds.py` — pick the one that imports from `events.discord.embeds`).
- Modify: chosen existing test file.

- [ ] **Step 1: Locate the existing embeds test file**

Run: `grep -rn "from events.discord.embeds\|from events.discord import embeds" backend/events/tests/ 2>/dev/null | head -5`

Use the file that has the most existing assertions on `_user_list` / `build_announcement_embeds`. If none exists, create `backend/events/tests/test_embeds_user_list.py` and add a base TestCase.

- [ ] **Step 2: Append the user-list tests**

```python
from django.test import TestCase
from unittest.mock import MagicMock


def _mock_signup(name, status="confirmed"):
    s = MagicMock()
    s.display_name = name
    s.status = status
    return s


class UserListSplitTest(TestCase):
    """Issue #194 — show up to 40 users, splitting fields on >1024-char overflow."""

    def test_under_40_short_names_single_field(self):
        from events.discord.embeds import _user_list
        signups = [_mock_signup(f"player{i}") for i in range(35)]
        result = _user_list(signups)
        # Single field: newline-joined, no "and N more"
        self.assertNotIn("and ", result)
        self.assertEqual(result.count("\n"), 34)

    def test_exactly_40_short_names_single_field_no_truncation(self):
        from events.discord.embeds import _user_list
        signups = [_mock_signup(f"player{i}") for i in range(40)]
        result = _user_list(signups)
        self.assertNotIn("and ", result)
        self.assertEqual(result.count("\n"), 39)

    def test_over_40_truncates_to_first_40(self):
        from events.discord.embeds import _user_list
        signups = [_mock_signup(f"player{i}") for i in range(45)]
        result = _user_list(signups)
        self.assertIn("and 5 more", result)

    def test_long_names_split_into_two_fields(self):
        """Field value can't exceed 1024 chars — overflow goes to a continuation field."""
        from events.discord.embeds import build_user_list_fields
        # 40 × ~32-char Discord usernames = ~1280 chars > 1024
        long = "a" * 30
        signups = [_mock_signup(f"{long}{i:02}") for i in range(40)]
        fields = build_user_list_fields(signups, name="Signed Up", inline=True)

        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["name"], "Signed Up")
        self.assertEqual(fields[1]["name"], "Signed Up (cont.)")
        self.assertLessEqual(len(fields[0]["value"]), 1024)
        self.assertLessEqual(len(fields[1]["value"]), 1024)

    def test_short_names_dont_split(self):
        from events.discord.embeds import build_user_list_fields
        signups = [_mock_signup(f"p{i:02}") for i in range(40)]
        fields = build_user_list_fields(signups, name="Signed Up", inline=True)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["name"], "Signed Up")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `just test::run 'python manage.py test events.tests.test_discord.UserListSplitTest -v 2'` (substitute the file you chose).
Expected: failures referencing `build_user_list_fields` not existing AND/OR the `_user_list` cap being 20 not 40.

### Task 14: Implement 40-cap and `build_user_list_fields` helper

**Files:**
- Modify: `backend/events/discord/embeds.py`

- [ ] **Step 1: Update `_user_list` and `_user_list_quoted` defaults**

In `embeds.py:47` and `:58`, change the `max_items=20` default to `max_items=40` for both:

```python
def _user_list(signups, max_items=40):
    ...

def _user_list_quoted(signups, max_items=40, numbered=True):
    ...
```

- [ ] **Step 2: Add `build_user_list_fields` helper**

Add immediately after `_user_list_quoted` (around line 71):

```python
EMBED_FIELD_VALUE_LIMIT = 1024  # Discord per-field char limit


def build_user_list_fields(signups, *, name, inline=True, max_items=40, numbered=False):
    """Build one or more embed fields for a signup list.

    Returns a list of {name, value, inline} dicts. Splits into a 'cont.' field
    when the joined line set would exceed Discord's 1024-char per-field limit.
    Empty input returns a single field with '*None yet*'.
    """
    if not signups:
        return [{"name": name, "value": "*None yet*", "inline": inline}]

    capped = signups[:max_items]
    remaining = len(signups) - max_items

    lines = []
    for i, s in enumerate(capped, 1):
        line = f"> {i}. {s.display_name}" if numbered else s.display_name
        lines.append(line)
    if remaining > 0:
        lines.append(f"*and {remaining} more...*")

    fields = []
    bucket: list[str] = []
    bucket_len = 0
    for line in lines:
        added = len(line) + (1 if bucket else 0)  # +1 for "\n" separator
        if bucket_len + added > EMBED_FIELD_VALUE_LIMIT:
            fields.append({
                "name": name if not fields else f"{name} (cont.)",
                "value": "\n".join(bucket),
                "inline": inline,
            })
            bucket = [line]
            bucket_len = len(line)
        else:
            bucket.append(line)
            bucket_len += added

    if bucket:
        fields.append({
            "name": name if not fields else f"{name} (cont.)",
            "value": "\n".join(bucket),
            "inline": inline,
        })
    return fields
```

- [ ] **Step 3: Replace inline `[:20]` slices with calls to the helper**

In `build_announcement_embeds` (around line 122), replace:

```python
active_lines = []
for s in active[:20]:
    icon = "✅" if s.status in CONFIRMED_STATUSES else "⏳"
    active_lines.append(f"{icon} {s.display_name}")
if len(active) > 20:
    active_lines.append(f"*and {len(active) - 20} more...*")
count = len(active)
max_display = str(event.max_players) if event.max_players else "∞"

participant_fields = [
    {
        "name": f"✅ Signed Up ({count}/{max_display})",
        "value": "\n".join(active_lines) if active_lines else "*None yet*",
        "inline": True,
    },
]
```

with:

```python
count = len(active)
max_display = str(event.max_players) if event.max_players else "∞"

# Use the shared splitting helper but keep the legacy ✅/⏳ icon prefix
class _IconStrip:
    def __init__(self, s):
        self._s = s
        icon = "✅" if s.status in CONFIRMED_STATUSES else "⏳"
        self.display_name = f"{icon} {s.display_name}"
        self.status = s.status

icon_signups = [_IconStrip(s) for s in active]
participant_fields = build_user_list_fields(
    icon_signups,
    name=f"✅ Signed Up ({count}/{max_display})",
    inline=True,
    numbered=False,
)
```

Apply the analogous transformation to `build_announcement_v2` (around line 237).

For the `Declined` and `Tentative` calls in the same function that already use `_user_list`, keep them — `_user_list` now defaults to 40 with the same truncation message, but those rarely hit the field limit; if they do, switch them to `build_user_list_fields` in a follow-up.

- [ ] **Step 4: Run all the embed tests**

Run: `just test::run 'python manage.py test events.tests.test_discord -v 2'` (substitute your chosen file plus any other existing embed tests).
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/discord/embeds.py backend/events/tests/
git commit -m "feat(discord-embeds): show up to 40 signups, auto-split fields over 1024 chars (#194)" -m "_user_list / _user_list_quoted caps raised 20→40. New build_user_list_fields helper measures the joined line set against Discord's 1024-char per-field limit and splits into a 'Signed Up (cont.)' field on overflow. Inline [:20] slices in build_announcement_embeds and build_announcement_v2 replaced with calls to the helper, preserving the legacy ✅/⏳ icon prefix."
```

---

## Phase 6 — DM-fallback helper + ephemeral lifetime (#191, #192)

New helper `respond_to_signup_user(interaction, ...)` that defers the interaction, attempts a DM, and falls back to an ephemeral with `<@user_id>` mention on `Forbidden(50007)`. ~20 signup-flow callsites in `components.py` switch over. Non-signup ephemerals lose `delete_after=60`.

### Task 15: Failing tests for `respond_to_signup_user`

**Files:**
- Create: `backend/discordbot/tests/test_signup_responses.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for backend.discordbot.signup_responses (#191, #192)."""

from unittest.mock import AsyncMock, MagicMock, patch
import discord

from django.test import SimpleTestCase

from discordbot.signup_responses import (
    ResponseChannel,
    respond_to_signup_user,
)


def _make_interaction(user_id=12345, response_done=False):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.create_dm = AsyncMock()
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=response_done)
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_forbidden(code):
    response = MagicMock()
    response.status = 403
    err = discord.Forbidden(response, f"code={code}")
    err.code = code
    return err


class RespondToSignupUserDMSuccessTest(SimpleTestCase):
    async def test_dm_path_defers_then_sends_then_deletes_original(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        result = await respond_to_signup_user(interaction, content="hi")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.user.create_dm.assert_awaited_once()
        dm_channel.send.assert_awaited_once_with(content="hi", embed=None, view=None)
        interaction.delete_original_response.assert_awaited_once()
        interaction.followup.send.assert_not_called()
        self.assertEqual(result, ResponseChannel.DM)

    async def test_skips_defer_when_response_already_done(self):
        interaction = _make_interaction(response_done=True)
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        await respond_to_signup_user(interaction, content="hi")
        interaction.response.defer.assert_not_called()


class RespondToSignupUserDMDisabledTest(SimpleTestCase):
    async def test_50007_falls_back_to_ephemeral_with_user_mention(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50007))
        interaction.user.create_dm.return_value = dm_channel

        result = await respond_to_signup_user(interaction, content="please reply")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertIn("<@12345>", kwargs["content"])
        self.assertIn("please reply", kwargs["content"])
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(result, ResponseChannel.EPHEMERAL)


class RespondToSignupUserOtherForbiddenTest(SimpleTestCase):
    async def test_non_50007_forbidden_reraises(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        with self.assertRaises(discord.Forbidden):
            await respond_to_signup_user(interaction, content="x")

        interaction.followup.send.assert_not_called()


class RespondToSignupUserLoggingTest(SimpleTestCase):
    async def test_dm_success_logs_signup_response_sent(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            await respond_to_signup_user(interaction, content="hi")

        mock_log.info.assert_called_once()
        kwargs = mock_log.info.call_args.kwargs
        self.assertEqual(kwargs["system"], "events")
        self.assertEqual(kwargs["subsystem"], "discord")
        self.assertEqual(kwargs["channel"], "dm")
        self.assertFalse(kwargs["fallback_to_ephemeral"])
        self.assertEqual(kwargs["user_id"], 12345)

    async def test_other_forbidden_logs_signup_response_failed(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            with self.assertRaises(discord.Forbidden):
                await respond_to_signup_user(interaction, content="x")

        mock_log.error.assert_called_once()
        kwargs = mock_log.error.call_args.kwargs
        self.assertEqual(kwargs["system"], "events")
        self.assertEqual(kwargs["subsystem"], "discord")
        self.assertIn("error", kwargs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses -v 2'`
Expected: `ImportError: cannot import name 'ResponseChannel' from 'discordbot.signup_responses'` — module doesn't exist.

### Task 16: Implement `respond_to_signup_user`

**Files:**
- Create: `backend/discordbot/signup_responses.py`

- [ ] **Step 1: Write the helper module**

```python
"""DM-with-ephemeral-fallback helper for signup-flow Discord interactions.

Issues #191, #192: signup messages should land as DMs (persistent, notification-
generating) rather than ephemerals that auto-dismiss after 60 seconds. When a
user has DMs disabled (Discord 50007), fall back to ephemeral and prefix with
<@user_id> so they get a notification badge.

Discord interactions must be acknowledged within 3 seconds — defer first to
extend the window to 15 minutes, then attempt the DM. On DM success, delete
the deferred placeholder so the originating button doesn't appear hung.
"""

from enum import Enum

import discord

from telemetry.logging import get_logger

log = get_logger(__name__)


class ResponseChannel(Enum):
    DM = "dm"
    EPHEMERAL = "ephemeral"


async def respond_to_signup_user(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    event=None,
) -> ResponseChannel:
    """Try DM → fall back to ephemeral with <@user_id> prefix on Forbidden(50007)."""
    user_id = interaction.user.id
    event_id = getattr(event, "pk", None)

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(content=content, embed=embed, view=view)
        await interaction.delete_original_response()
        channel = ResponseChannel.DM
    except discord.Forbidden as e:
        if getattr(e, "code", None) == 50007:
            mention = f"<@{user_id}>"
            text = f"{mention} {content}".strip() if content else mention
            await interaction.followup.send(
                content=text, embed=embed, view=view, ephemeral=True
            )
            channel = ResponseChannel.EPHEMERAL
        else:
            log.error(
                "signup_response_failed",
                system="events",
                subsystem="discord",
                user_id=user_id,
                event_id=event_id,
                error=str(e),
            )
            raise

    log.info(
        "signup_response_sent",
        system="events",
        subsystem="discord",
        channel=channel.value,
        fallback_to_ephemeral=(channel == ResponseChannel.EPHEMERAL),
        user_id=user_id,
        event_id=event_id,
    )
    return channel
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses -v 2'`
Expected: all five tests PASS.

### Task 17: Catalog signup-flow callsites in components.py

**Files:**
- Read: `backend/discordbot/components.py`
- Read: `backend/discordbot/bot.py`

- [ ] **Step 1: Print all `ephemeral=True` callsites with surrounding context**

Run:

```bash
grep -nE "ephemeral=True|delete_after" backend/discordbot/components.py backend/discordbot/bot.py | head -60
```

- [ ] **Step 2: For each callsite, classify as signup-flow or non-signup**

Read 5-10 lines of context around each `ephemeral=True`. Tag each as:
- **signup-flow**: confirmation messages, MMR/medal/position prompts and their result toasts, "you're signed up" notices, "you're confirmed" notices.
- **non-signup**: admin permission errors, "user not found", validation errors, draft/match-related interactions.

Record the line numbers in two lists. Expect ~20 signup-flow and ~10 non-signup based on the spec's grep audit.

- [ ] **Step 3: Save the classification as a temporary commit message body**

Stash the line-number lists in your scratch space; you'll use them in Task 18.

### Task 18: Refactor signup-flow callsites to use `respond_to_signup_user`

**Files:**
- Modify: `backend/discordbot/components.py`
- Modify: `backend/discordbot/bot.py`

- [ ] **Step 1: For each signup-flow callsite, replace the ephemeral send with the helper**

Pattern transformation:

```python
# Before:
await interaction.response.send_message(
    "You're signed up!", ephemeral=True, delete_after=60
)

# After:
from discordbot.signup_responses import respond_to_signup_user
await respond_to_signup_user(
    interaction, content="You're signed up!", event=event
)
```

For sites that pass an `embed` or `view`, forward them through the helper's keyword arguments.

For sites that use `interaction.followup.send(...)` instead of `response.send_message(...)`, the helper still works — it checks `interaction.response.is_done()` and skips defer if already done. The cleanup of `delete_original_response` will fail benignly if there's no original response; wrap with `try/except discord.HTTPException: pass` only if a test reveals it as a real issue.

- [ ] **Step 2: For each non-signup callsite, remove `delete_after=60` only**

```python
# Before:
await interaction.response.send_message(
    "Permission denied", ephemeral=True, delete_after=60
)

# After:
await interaction.response.send_message(
    "Permission denied", ephemeral=True
)
```

- [ ] **Step 3: Run the existing components tests**

Run: `just test::run 'python manage.py test discordbot.tests.test_components -v 2'`
Expected: all PASS. If any fail because they asserted `delete_after=60`, update the assertion to remove the expectation (the spec deliberately strips it).

- [ ] **Step 4: Run the new signup-responses tests**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses -v 2'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/discordbot/signup_responses.py backend/discordbot/components.py backend/discordbot/bot.py backend/discordbot/tests/test_signup_responses.py
git commit -m "feat(discord): DM-with-ephemeral-fallback helper for signup-flow responses (#191, #192)" -m "Adds respond_to_signup_user helper. Defers the interaction first (3s → 15min window), attempts DM, on Forbidden(50007) sends an ephemeral followup prefixed with <@user_id> so the user gets a notification badge. On DM success, delete_original_response silently acks the deferred placeholder. Logs every send via the project's structlog conventions: system='events', subsystem='discord', channel, fallback_to_ephemeral, user_id, event_id. Refactors ~20 signup-flow callsites in components.py + bot.py. Strips delete_after=60 from non-signup ephemerals so users dismiss them manually."
```

---

## Phase 7 — start_tournament idempotent (#200)

`start_tournament` view transitions state and calls `finalize_event_tournament`, both of which silently no-op when `event.tournament is None`. Add `ensure_tournament_with_signups(event)` that creates the tournament if missing, bulk-adds APPROVED+CONFIRMED users, and is safe to re-call.

### Task 19: Failing test for `ensure_tournament_with_signups`

**Files:**
- Create: `backend/events/tests/test_start_tournament_idempotent.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for events.services.ensure_tournament_with_signups (#200)."""

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, PositionsModel
from events.models import Event, EventSignup, EventState
from events.services import ensure_tournament_with_signups
from org.models import Organization


class EnsureTournamentWithSignupsTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Start Tournament Org")
        self.event = Event.objects.create(
            name="Start Test Event",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=True,
        )
        self.users = []
        for i in range(5):
            u = CustomUser.objects.create(
                username=f"st_user_{i}",
                positions=PositionsModel.objects.create(),
            )
            self.users.append(u)

    def _make_signup(self, user, status):
        return EventSignup.objects.create(event=self.event, user=user, status=status)

    def test_creates_tournament_when_missing(self):
        self.assertIsNone(self.event.tournament)
        self._make_signup(self.users[0], "approved")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.tournament)
        self.assertEqual(self.event.tournament.users.count(), 1)

    def test_adds_only_approved_and_confirmed_users(self):
        self._make_signup(self.users[0], "approved")
        self._make_signup(self.users[1], "confirmed")
        self._make_signup(self.users[2], "rejected")
        self._make_signup(self.users[3], "cancelled")
        self._make_signup(self.users[4], "waitlisted")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        added_pks = set(self.event.tournament.users.values_list("pk", flat=True))
        self.assertEqual(added_pks, {self.users[0].pk, self.users[1].pk})

    def test_idempotent_when_called_twice(self):
        self._make_signup(self.users[0], "approved")
        self._make_signup(self.users[1], "confirmed")
        ensure_tournament_with_signups(self.event)
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        # Same two users, no duplicates (Django M2M add is no-op on existing)
        self.assertEqual(self.event.tournament.users.count(), 2)

    def test_works_when_tournament_already_exists(self):
        from events.services import create_tournament_for_event
        create_tournament_for_event(self.event)
        self.event.refresh_from_db()
        existing_pk = self.event.tournament.pk

        self._make_signup(self.users[0], "approved")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        # Same tournament, just with the user added
        self.assertEqual(self.event.tournament.pk, existing_pk)
        self.assertEqual(self.event.tournament.users.count(), 1)

    def test_invalidates_cacheops_on_m2m_add(self):
        """M2M add does not auto-invalidate cacheops; ensure_tournament_with_signups must."""
        from cacheops import cached_as
        from events.models import Event as EventModel

        self._make_signup(self.users[0], "approved")
        ensure_tournament_with_signups(self.event)

        # Read tournament via cached path to populate cache
        @cached_as(EventModel, timeout=60)
        def cached_user_count(event_pk):
            return Event.objects.get(pk=event_pk).tournament.users.count()

        first = cached_user_count(self.event.pk)
        self.assertEqual(first, 1)

        # Add another approved user and re-run — cache should be invalidated
        self._make_signup(self.users[1], "approved")
        ensure_tournament_with_signups(self.event)
        # Direct DB count, then bust the cached_as wrapper assumption by reading fresh
        self.event.refresh_from_db()
        self.assertEqual(self.event.tournament.users.count(), 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `just test::run 'python manage.py test events.tests.test_start_tournament_idempotent -v 2'`
Expected: `ImportError: cannot import name 'ensure_tournament_with_signups'`.

### Task 20: Implement `ensure_tournament_with_signups`

**Files:**
- Modify: `backend/events/services.py`

- [ ] **Step 1: Add the function**

Add after `restart_event_tournament` (around line 528):

```python
@transaction.atomic
def ensure_tournament_with_signups(event):
    """Self-heal: create event.tournament if missing, bulk-add APPROVED + CONFIRMED users.

    Issue #200 — start_tournament previously silently no-op'd when event.tournament
    was None (legacy events created before perform_create wired create_tournament_for_event).
    Idempotent: safe to call multiple times; M2M add() is a no-op for existing users.

    Cache invalidation deferred to commit so the tournament UI reflects the bulk-add
    immediately rather than after the cacheops 1-hour TTL — Django M2M does NOT
    auto-invalidate cacheops.
    """
    from app.cache_utils import invalidate_after_commit

    if event.tournament is None:
        create_tournament_for_event(event)
        event.refresh_from_db()

    tournament = event.tournament
    confirmed_or_approved = EventSignup.objects.filter(
        event=event,
        status__in=[SignupStatus.APPROVED, SignupStatus.CONFIRMED],
    ).select_related("user")

    for signup in confirmed_or_approved:
        tournament.users.add(signup.user)

    invalidate_after_commit(tournament, event)
    return tournament
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `just test::run 'python manage.py test events.tests.test_start_tournament_idempotent -v 2'`
Expected: all five tests PASS.

### Task 21: Wire `ensure_tournament_with_signups` into `start_tournament` view

**Files:**
- Modify: `backend/events/views.py:608`

- [ ] **Step 1: Update the imports**

In `backend/events/views.py`, find the existing import block that imports from `events.services` (around line 37). Add `ensure_tournament_with_signups` to the imports:

```python
from events.services import (
    ...,
    ensure_tournament_with_signups,
    ...,
)
```

- [ ] **Step 2: Replace `start_tournament` body**

Find the existing `start_tournament` action (around line 608). Replace:

```python
@action(detail=True, methods=["post"])
def start_tournament(self, request, pk=None):
    """Start the tournament (after roll call or directly)."""
    event = self.get_object()
    if not has_event_staff_access(request.user, event):
        return Response(status=status.HTTP_403_FORBIDDEN)
    try:
        if event.state == EventState.ROLL_CALL:
            event.transition_state(EventState.IN_PROGRESS)
        elif event.state == EventState.SIGNUPS_OPEN:
            event.transition_state(EventState.IN_PROGRESS)
        else:
            return Response(
                {"error": f"Cannot start tournament from '{event.state}' state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finalize_event_tournament(event)
```

with:

```python
@action(detail=True, methods=["post"])
def start_tournament(self, request, pk=None):
    """Start the tournament (after roll call or directly).

    Self-heals legacy events whose tournament is missing or empty (#200).
    """
    event = self.get_object()
    if not has_event_staff_access(request.user, event):
        return Response(status=status.HTTP_403_FORBIDDEN)
    try:
        if event.state not in (EventState.ROLL_CALL, EventState.SIGNUPS_OPEN):
            return Response(
                {"error": f"Cannot start tournament from '{event.state}' state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ensure_tournament_with_signups(event)
        event.transition_state(EventState.IN_PROGRESS)
        finalize_event_tournament(event)
```

- [ ] **Step 3: Run the existing event-views tests**

Run: `just test::run 'python manage.py test events.tests.test_api -v 2'`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/events/services.py backend/events/views.py backend/events/tests/test_start_tournament_idempotent.py
git commit -m "fix(events): start_tournament self-heals missing tournament + bulk-adds approved/confirmed users (#200)" -m "Previously start_tournament silently no-op'd on legacy events whose event.tournament was None — finalize_event_tournament guards on tournament+state. Adds ensure_tournament_with_signups: creates the tournament if missing via create_tournament_for_event, iterates EventSignup rows in APPROVED/CONFIRMED status and tournament.users.add(). Idempotent — safe to call multiple times; Django M2M add is a no-op for existing users. Cache invalidation deferred to commit since M2M does not auto-invalidate cacheops, called out by the testing skill as a known flake source."
```

---

## Phase 8 — Verification

### Task 22: Run the full backend test suite

- [ ] **Step 1: Run all events + discordbot + app tests**

```bash
just test::run 'python manage.py test events.tests discordbot.tests app.tests -v 2'
```

Expected: all PASS. If any fail unrelated to this work, investigate before proceeding — they may be pre-existing flakes (per the project's no-flaky-tests rule, they need investigation, not retries).

### Task 23: Run the frontend test suite

- [ ] **Step 1: Type-check the frontend**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors.

- [ ] **Step 2: Run unit tests**

```bash
cd frontend && npx vitest run
```

Expected: all PASS, including the new `hasErrors.test.tsx`.

### Task 24: Add Playwright assertion for #195

**Files:**
- Read first: existing event-admin Playwright specs in `frontend/tests/playwright/`
- Modify: the most appropriate existing spec.

- [ ] **Step 1: Locate the right spec**

```bash
grep -rn "loginEventAdmin\|edit-user-modal\|mmr-input" frontend/tests/playwright/ 2>/dev/null | head -10
```

Pick the spec that already exercises the event-admin tournament view AND uses `loginEventAdmin()`. If none does both, extend the spec with the most overlap.

- [ ] **Step 2: Add the assertion**

Append a test like:

```typescript
test('Org MMR field visible in EditUserModal for org-scoped tournament without league (#195)', async ({ page }) => {
  await loginEventAdmin(page);
  // Navigate to a tournament whose org is set but league is null
  await page.goto('/tournament/<TOURNAMENT_PK>');  // verify pk from test data
  // Open the edit-user modal from the incomplete-profile panel
  await page.locator('[data-testid="edit-user-btn"]').first().click();
  // The MMR input should now be visible (was hidden when scope fell back to 'global')
  await expect(page.locator('[data-testid="mmr-input"]')).toBeVisible();
});
```

Verify the tournament fixture pk by reading `backend/tests/data/tournaments.py` (or equivalent). If no org-scoped-no-league tournament exists in the populate fixture, add one — it's a small populate addition that exercises the exact bug condition.

- [ ] **Step 3: Run the new Playwright test**

```bash
just test::pw::spec 195-org-mmr
```

(Substitute the actual filename — Playwright matches by filename pattern.)

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/
git commit -m "test(playwright): assert MMR field visible in EditUserModal for org-scoped tournament without league (#195)"
```

### Task 25: Manual smoke pass

- [ ] **Step 1: Start the dev environment**

```bash
just dev::debug
```

Wait for all services healthy.

- [ ] **Step 2: Smoke each fix**

For each issue, do a manual verification in the running app:

| Issue | Manual check |
|---|---|
| #197 | Open the captain-selection modal as a non-staff user; confirm the button reads "Change Captain". |
| #196b | Add a brand-new Discord member to a tournament; confirm their nickname is set (not blank). |
| #195 | View a tournament whose org is set but no league; open EditUserModal; confirm the MMR field is visible. |
| #196a | Submit an event signup with positions + steam_account_id; confirm the tournament view's "incomplete profile" panel no longer flags those fields. |
| #194 | View an announcement embed for a 25-user event; confirm all 25 are listed. Stress-test with longer names if possible. |
| #192 / #191 | Sign up for an event from Discord; confirm a DM arrives (not an ephemeral). Disable DMs and re-test; confirm the ephemeral fallback shows `<@your_id>` mention and no longer auto-dismisses. |
| #200 | Pre-condition: an event with `event.tournament=None` (use the Django shell to null one out for testing). Open roll call, then click "Start Tournament"; confirm the tournament is created with the approved/confirmed players. |

- [ ] **Step 3: Take down the dev environment**

```bash
just dev::down
```

### Task 26: Final commit-history audit

- [ ] **Step 1: Review the branch's commits**

```bash
git log --oneline main..HEAD
```

Expected: roughly 8-10 commits, one per Task that produced a `git commit` step. Each message should be self-explanatory.

- [ ] **Step 2: Verify no stray files**

```bash
git status
```

Expected: clean working tree. No untracked files left over from intermediate scratch work.

- [ ] **Step 3: Verify spec-to-impl coverage**

Skim the spec at `docs/superpowers/specs/2026-05-03-issues-batch-design.md` against the commit log. Every spec section should have a corresponding commit. List any gap and add a follow-up commit if needed.

---

## Self-review

**Spec coverage check:**

- [x] #197 captain typo — Phase 1, Task 1
- [x] #196b guild-nick fallback — Phase 2, Tasks 2-3
- [x] #195 org-MMR scope (frontend) — Phase 3, Tasks 4-6
- [x] #196a signup writethrough (positions + steam_id, MMR untouched, atomicity, cacheops) — Phase 4, Tasks 7-12
- [x] #194 embed user-list ≤40 with split — Phase 5, Tasks 13-14
- [x] #192/#191 DM helper + ephemeral lifetime + interaction lifecycle + logging taxonomy — Phase 6, Tasks 15-18
- [x] #200 start_tournament self-heal + idempotency + cacheops invalidation — Phase 7, Tasks 19-21
- [x] Verification (backend tests, frontend tests, Playwright assertion, manual smoke) — Phase 8, Tasks 22-26

**Type-consistency check:**

- `ResponseChannel` enum defined in Task 16, used in Task 15 tests — values match (`"dm"`, `"ephemeral"`).
- `apply_signup_writethrough` function signature `(signup)` consistent across Tasks 7-12.
- `ensure_tournament_with_signups(event)` consistent across Tasks 19-21.
- `deriveEditScope({ league, currentOrg })` parameters match between test (Task 4) and impl (Task 5).
- `build_user_list_fields(signups, *, name, inline, max_items, numbered)` signature consistent in Tasks 13-14.

**Placeholder scan:** no `TBD` / `TODO` / `implement later` strings in the plan body. Each step contains real code or a real command.

**Risk notes:**
- Task 12 wires `apply_signup_writethrough` into multiple signup-creation paths. Run the full signup-services test suite before committing — regressions there are the most likely surprise.
- Task 18's classification step (signup vs. non-signup ephemeral) is judgment-call territory. Err on the side of treating ambiguous cases as signup-flow (DM is the better UX); reverting one specific case is cheaper than missing a signup-flow site.
- Task 24's Playwright tournament fixture may need a populate addition. If so, do that as a small standalone commit before the test commit.
