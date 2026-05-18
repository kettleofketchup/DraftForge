# User Profile Entity Adapter — Epic Design

**Date:** 2026-05-17 (revised 2026-05-18 — multi-reviewer pass 2)
**Status:** Draft (spec); awaiting user review
**Owner:** Mark Paxson
**Branch:** TBD (will branch from `main`); each child ticket gets its own branch
**Epic ticket:** [#224](https://github.com/kettleofketchup/DraftForge/issues/224) (to be rewritten as the epic per this spec)

## Summary

Split user profile data into a layered model — `BaseUserProfile` (single-value user data), `DotaUserProfile` / `DeadlockUserProfile` (per-user, per-game defaults), `OrgUserProfile` (per-org hub), and `OrgDotaUserProfile` / `OrgDeadlockUserProfile` (per-org game overrides) — and add a `userProfileEntityAdapter` on the frontend mirroring the existing `userAdapter` pattern. Context (active game from `gameTypeStore`, active `orgUser.pk` from route) drives field resolution so a player can carry in Org A, support in Org B, and have user-wide Dota defaults that aren't tied to either org.

The epic is sliced into three independently shippable, per-layer vertical tickets (T1 Base, T2 Dota/Deadlock user-wide, T3 Org + org-game). Each ticket ships its own model migration, adapter layer, backend endpoints, and an additive modal tab. After every ticket the app is fully usable.

## Motivation

Today, `CustomUser` (`backend/app/models.py:92`) directly owns single-game data — most notably `positions` (FK to `PositionsModel`) and Dota MMR verification timestamps. This conflates three layers of identity:

1. **User-global identity** (single-value): `nickname`, `avatar`, Discord/Steam IDs.
2. **Game-specific user identity** (per game, user-wide): default positions in Dota, role preferences in Deadlock, game-wide MMR verification.
3. **Org-scoped game identity** (per OrgUser, per game): "I play hard support in Org A but carry in Org B." Partially exists via `PlayerDotaProfile` / `PlayerDeadlockProfile` (`backend/org/models_profiles.py`) attached to `OrgUser`.

Because positions live on `CustomUser`, the same user cannot have different position preferences in different orgs without overwriting their global defaults. Game-specific user-wide defaults have nowhere to live separate from per-org data. Related broader scoping problem tracked in [#202](https://github.com/kettleofketchup/DraftForge/issues/202).

On the frontend, `userAdapter` (`frontend/app/store/userCacheStore.ts:62`) already separates core identity from `orgData` / `leagueData` context overlays, but exposes `positions` flat on `UserEntry`, forcing callers to remember which layer they should be reading from for their view's context.

## Non-goals

- **No new game-type support.** This epic shapes the model so adding games is cheap, but ships only the existing `GameType` values (Dota 2, Deadlock).
- **No changes to `userAdapter` core shape.** `UserEntry.nickname`, `.avatar`, etc. continue to be flattened by the backend serializer that ships user identity to list endpoints; `userAdapter` keeps its current API. The new adapter is additive.
- **No new editable fields beyond migration.** Each ticket moves existing fields to their new home; no fields are added (except `OrgUserProfile`, which intentionally starts empty as a placeholder hub).
- **No discord-side or steam-side identity refactor.** `CustomUser.steam_account_id`, `discordId`, `username` all stay on `CustomUser` as identity, not profile.
- **No bulk-edit UI.** Modal edits one user (the current user) at a time.
- **No data backfill from sources beyond the existing rows.** If `CustomUser.nickname` is `NULL` today, `BaseUserProfile.nickname` will be `NULL` after T1.
- **No `CustomUser` move into the `user` app.** A follow-up epic moves `CustomUser` into `backend/user/`; this epic only lands the new profile models in the existing `user` app (created in commit `1ceeb9f9`).

## Architecture

### Backend model hierarchy

```
CustomUser ─1:1─< BaseUserProfile
                     ↑
                     └─1:1─ DotaUserProfile        (FK → BaseUserProfile)
                            DeadlockUserProfile    (FK → BaseUserProfile)

OrgUser ─1:1─< OrgUserProfile
                  ↑
                  └─1:1─ OrgDotaUserProfile        (FK → OrgUserProfile, renamed from PlayerDotaProfile)
                         OrgDeadlockUserProfile    (FK → OrgUserProfile, renamed from PlayerDeadlockProfile)
```

- Every profile FKs to exactly one parent. No denormalized `CustomUser` FK on the org side; the chain `OrgDotaUserProfile.org_user_profile.org_user.user` reaches the user with one extra JOIN.
- `BaseUserProfile` is created when a `CustomUser` is created (auto-create hook on `CustomUser.save()`).
- `OrgUserProfile` is created when an `OrgUser` is created. Starts essentially empty; designed to grow.
- Game profiles auto-created the first time the parent profile is saved.

**Existing Django app `user` (created in commit `1ceeb9f9`).** All new profile models land in `backend/user/`, which is already registered in `INSTALLED_APPS` as `user.apps.UserConfig`. T1 extends the existing app — it does NOT create it from scratch. Long-term intent (out of scope here): `CustomUser` itself moves into `backend/user/` in a follow-up epic.

**`related_name` discipline on new positions FKs (T2 constraint).** `PositionsModel.save()`'s invalidation chain (see "Cache invalidation" below) walks `self.dotauserprofile_set` and `self.orgdotauserprofile_set` — Django's default reverse accessor names. New positions FKs in T2 MUST be declared with NO explicit `related_name` (default applies) OR with explicit `related_name="dotauserprofile_set"` / `"orgdotauserprofile_set"`. Any other value silently breaks the invalidation loop. Hard constraint in T2 acceptance.

### Frontend adapter shape

New files alongside `userCacheStore.ts`:

- `frontend/app/store/userProfileStore.ts` — Zustand store + `userProfileEntityAdapter` instance.
- `frontend/app/store/userProfileTypes.ts` — `UserProfileEntry`, `BaseProfile`, `DotaUserProfile`, etc.

```ts
interface UserProfileEntry {
  pk: number;                              // = CustomUser.pk (same key as userAdapter)
  base: BaseProfile;                       // always present when entry exists
  gameUser: {
    dota?: DotaUserProfile;
    deadlock?: DeadlockUserProfile;
  };
  orgProfiles: Record<number, {            // keyed by orgUser.pk
    orgUser: OrgUserProfile;
    dota?: OrgDotaUserProfile;
    deadlock?: OrgDeadlockUserProfile;
  }>;
  _fetchedAt: number;
}
```

**Middleware:** `devtools` (matches the existing `userCacheStore.ts:2` pattern). `immer` is NOT currently used in `frontend/app/store/` and is NOT in `frontend/package.json`. The new store either (a) adds `immer` as a dependency for nested writes (recommended given `orgProfiles[orgUserId][gameType]` depth), or (b) hand-writes the spread chain like `userCacheStore.ts:86-106`. T1 implementation makes the call; the spec does not pretend `immer` matches existing precedent. **No `persist`** (auth-scoped, fetched on demand). **No `subscribeWithSelector`** — pull model (hooks read both stores).

**Custom `hasChanged`:** the default `createEntityAdapter` `hasChanged` walks only schema `coreKeys`, which would silently drop nested updates to `gameUser` / `orgProfiles`. New store ships a custom `hasChanged` comparing `base` (shallow), each `gameUser[game]` slot, and each `orgProfiles[orgUserId]` slot — same workaround `userCacheStore.ts:41-60` (`hasScopedChanged`) uses for `orgData` / `leagueData`.

**Lifecycle:**
- `staleAfterMs`: 5 minutes. TanStack Query `staleTime` matches.
- `reset()` on logout: explicitly wired to the logout flow (matches `userCacheStore.ts:253`).

### Resolution rule

For any layered field (positions, game MMR refs, etc.):

```
field = orgProfiles[orgUserId]?.[gameType]?.field
     ?? gameUser[gameType]?.field
     ?? undefined                          // base never holds game-specific fields
```

For base-only fields (nickname, avatar): read `base.field` directly.

**Context inputs:**
- `gameType` — read from `frontend/app/store/gameTypeStore.ts` (the active view's game).
- `orgUserId` — read from route context. Hooks resolve via existing route helpers; selectors take it as an explicit arg.

**`gameType === null` fallback.** When no active game is set, `selectPositions` returns `undefined`. Never a silent default to Dota.

### Frontend hook & data-loading contract

Consumers resolving a layered field MUST go through these hooks/selectors.

**Selector signatures (primitive args, not an object) so memoization downstream works:**

```ts
selectPositions(
  state: UserProfileState,
  userPk: number,
  gameType: GameType | null,
  orgUserId?: number,
): PositionsType | undefined;

selectMmrSnapshot(state, userPk, gameType, orgUserId): MmrSnapshot | undefined;
```

**Hooks use primitive selectors + `useShallow` on resolved-object reads:**

```ts
import { useShallow } from 'zustand/react/shallow';  // explicit import — not auto-included

function usePlayerPositions(userPk: number): PositionsType | undefined {
  const gameType  = useGameTypeStore(s => s.activeGame);   // primitive
  const orgUserId = useRouteOrgUserId();                   // primitive | undefined
  return useUserProfileStore(useShallow(s =>
    selectPositions(s, userPk, gameType, orgUserId)
  ));
}
```

Pull model: the hook subscribes to both stores; React re-renders when either changes. No `subscribeWithSelector` on `gameTypeStore`.

**Data loading: `<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery`.** TanStack Query already in use (`@tanstack/react-query@5.90.16`, `QueryClientProvider` mounted in `frontend/app/root.tsx`). `useSuspenseQuery` throws errors into the React tree, so `<ErrorBoundary>` MUST wrap the `<Suspense>` boundary — without it, a 401/500 propagates uncaught:

```tsx
function EditProfileModal({ userPk }: Props) {
  return (
    <ErrorBoundary fallback={<ProfileErrorFallback />}>
      <Suspense fallback={<ProfileSkeleton />}>
        <EditProfileModalBody userPk={userPk} />
      </Suspense>
    </ErrorBoundary>
  );
}

function EditProfileModalBody({ userPk }: Props) {
  const { data } = useSuspenseQuery({
    queryKey: ['userProfile', userPk],
    queryFn: () => api.getUserProfile(userPk),
    staleTime: 5 * 60 * 1000,    // matches Zustand staleAfterMs
    gcTime:    10 * 60 * 1000,
  });
  // Write-through to Zustand happens in useEffect, NOT in select (select must be pure).
  useEffect(() => {
    useUserProfileStore.getState().upsert(data);
  }, [data]);
  return <ProfileTabs profile={data} />;
}
```

**`select` MUST be pure.** Earlier drafts suggested `useUserProfileStore.getState().upsert(raw)` inside `select` — that's a side-effect inside a render-phase memoizer, an anti-pattern in TanStack Query v5. Write-through goes in `useEffect`.

**PATCH uses `useMutation`, not `useActionState`.** This is a SPA hitting Django REST — no progressive-enhancement story preserved by `useActionState`. `useMutation` integrates with `queryClient.invalidateQueries(['userProfile', userPk])` in `onSuccess`, exposes `isPending`/`error`/`mutate`, and is the idiomatic React 19 + TanStack Query v5 pattern. Dual-write to `userAdapter` lives in `mutation.onSuccess`:

```ts
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: (patch: BasePatchPayload) => patchBaseProfile(patch),
  onSuccess: (updated) => {
    // 1. Dual-write to userAdapter so UserCard refreshes in the same microtask.
    useUserCacheStore.getState().upsert({
      pk: profile.pk,
      nickname: updated.nickname ?? null,
      avatar:   updated.avatar   ?? null,
    });
    // 2. Mark the profile query stale so the next read refetches.
    queryClient.invalidateQueries({ queryKey: ['userProfile', profile.pk] });
    toast.success('Profile updated');
    onClose();
  },
  onError: (err) => {
    log.error('base_patch_failed', { userPk: profile.pk, error: String(err) });
    Sentry.captureException(err, {
      tags: { system: 'users', subsystem: 'profile' },
      extra: { userPk: profile.pk },
    });
    toast.error('Failed to update profile');
  },
});
// form.handleSubmit(values => mutation.mutate(values))
```

**Lazy-mount tabs via `React.lazy`** — RHF + Zod resolvers don't instantiate for tabs the user never opens (critical once T3 adds N org tabs).

**Suspense INSIDE each `<TabsContent>`** — per-tab code-load fallback doesn't unmount the surrounding `<Tabs>` UI on tab switch:

```tsx
<TabsContent value="base">
  <Suspense fallback={<TabSkeleton />}>
    <BaseTab profile={data} onClose={onClose} />
  </Suspense>
</TabsContent>
```

### Backend endpoints

All additive. Existing `UpdateProfile` (`frontend/app/components/api/api.ts` → `PATCH /users/me/`) stays alive through T1, retired in T2 when the layered Dota PATCH replaces it.

| Endpoint | Returns / Accepts |
|---|---|
| `GET  /api/users/me/profile/` | Full `UserProfileEntry` shape (base + gameUser + orgProfiles). |
| `PATCH /api/users/me/profile/base/` | Partial `BaseUserProfile` fields. |
| `PATCH /api/users/me/profile/game/{game}/` | Partial `<Game>UserProfile` fields. |
| `PATCH /api/org-users/{org_user_pk}/profile/` | Partial `OrgUserProfile` fields. |
| `PATCH /api/org-users/{org_user_pk}/profile/game/{game}/` | Partial `Org<Game>UserProfile` fields. |

Authorization: every endpoint scoped to "the current user can edit their own profile." Org-scoped PATCHes additionally require an `OrgUser` membership row.

**Backend view logging (mandatory).** Every endpoint emits structured logs matching the project's structlog convention (signature reference: `backend/app/views/bracket.py`):

```python
log = structlog.get_logger(__name__)

# GET (high-volume, modal open)
log.debug("profile_fetched", system="user", subsystem="profile", user_id=request.user.id)

# PATCH (success)
log.info("profile_base_patched", system="user", subsystem="profile",
         user_id=request.user.id,
         fields_changed=sorted(serializer.validated_data.keys()))

# PATCH (validation error)
log.warning("profile_base_patch_invalid", system="user", subsystem="profile",
            user_id=request.user.id, errors=serializer.errors)
```

GET at DEBUG, PATCH at INFO. Never log avatar URL content or nickname diffs — keys only.

### Cache invalidation & cacheops integration

The new model layer changes which rows must be invalidated when which fields change. Cacheops handles row-level caching automatically once a model is listed in `CACHEOPS` (`backend/backend/settings.py`), but the existing chain from `PositionsModel` saves to `CustomUser` cache (`backend/app/models.py:48-53`) **breaks** when positions move off `CustomUser` in T2 and must be rewritten.

**CACHEOPS entries to add (`settings.py`):**

| Model | Ticket | Add? | Reason |
|---|---|---|---|
| `user.baseuserprofile` | T1 | Yes | Read on every list endpoint shipping `nickname` / `avatar`. App label is `users` (new app). |
| `user.dotauserprofile` | T2 | Yes | Read by Dota draft / tournament / team-card views. |
| `user.deadlockuserprofile` | T2 | Yes | Parity with Dota. |
| `org.orguserprofile` | T3 | No (defer) | Empty placeholder; add when fields land. |
| `org.orgdotauserprofile` | T3 | Yes (rename) | Renamed from `org.playerdotaprofile` — the CACHEOPS key MUST be renamed in `settings.py` in the same PR or caching silently disables. |
| `org.orgdeadlockuserprofile` | T3 | Yes (rename) | Renamed from `org.playerdeadlockprofile`. |

**`PositionsModel.save()` rewrite (T2, classed as a blocker):**

After T2, `PositionsModel.customuser_set` is empty — the existing invalidation loop becomes a no-op and cached `CustomUser` / `OrgDotaUserProfile` rows stay stale until the 1h TTL elapses. T2 MUST rewrite the loop to walk the new owners (using the default `related_name` accessors per the discipline note above):

```python
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    dota_profiles = list(self.dotauserprofile_set.all())
    org_profiles  = list(self.orgdotauserprofile_set.all())
    for profile in dota_profiles:
        invalidate_obj(profile)
        invalidate_obj(profile.base_profile.user)
    for org_profile in org_profiles:
        invalidate_obj(org_profile)
        invalidate_obj(org_profile.org_user_profile.org_user)
    log.debug("positions_invalidated", system="user", subsystem="cache",
              positions_id=self.pk,
              dota_profiles=len(dota_profiles),
              org_dota_profiles=len(org_profiles))
```

**`@cached_as` decorator updates (T1) — enumerate, not blanket.** Every `@cached_as(CustomUser, ...)` call site in `backend/app/views_main.py` (currently 14+ sites including lines 192-1199) AND `backend/app/functions/tournament.py:456` that ships `nickname` or `avatar` must also depend on `BaseUserProfile`:

```python
from user.models import BaseUserProfile

@cached_as(CustomUser, BaseUserProfile, ...)
def get_user_list(...):
    ...
```

**T1 grep guardrail acceptance:** `rg "@cached_as\(.*CustomUser" backend/app/ backend/user/ | rg -v "BaseUserProfile"` returns zero lines (every remaining un-updated site is a defect).

**`bulk_update` / `bulk_create` invariant for data migrations.** If any T1/T2/T3 data migration uses `bulk_update` or `bulk_create` (likely for T1's backfill at scale), cacheops post-save signals are NOT fired — the migration MUST follow up with explicit `invalidate_model(CustomUser); invalidate_model(BaseUserProfile)` after the bulk write.

**Disable cacheops during data migrations.** Data migrations call `cache.clear()` (or set `CACHEOPS_ENABLED=False` for the duration) at start to avoid mid-migration cache poisoning, and call `invalidate_all()` at the end to ensure a clean post-migration cache state.

**Auto-create within `transaction.atomic()`:** `BaseUserProfile.save()` auto-creating `DotaUserProfile`/`DeadlockUserProfile`, and `OrgUser.save()` auto-creating `OrgUserProfile`, run nested `INSERT`s inside the parent's save transaction. To avoid out-of-order cache state, use `invalidate_after_commit()` (from `backend/app/cache_utils.py:20`) rather than direct `invalidate_obj()` for child creations.

**`CustomUser.positions` shim — read + write (T2).** The shim is NOT read-only. Property has both a getter (proxying to `dota_user_profile.positions`) AND a setter (writing to `dota_user_profile.positions` AND calling `invalidate_after_commit(dota_user_profile)`). Same pattern as the T1 transitional setters for `nickname`/`avatar`. This lets populate fixtures and any unmigrated writers keep working without churn until the shim is removed in a cleanup ticket.

**Tests:** each ticket includes a cacheops integration test in its own module (e.g. `backend/user/tests/test_cacheops.py`) that:
1. Calls `cache.clear()` in `setUp` and `invalidate_all()` in `tearDown` (parallel-test safety).
2. Warms a cached list endpoint (a `@cached_as(CustomUser, BaseUserProfile, ...)` view).
3. PATCHes the relevant new model.
4. Re-fetches the list and asserts the change is reflected.
5. Uses feature-isolated users (e.g. `USER_EDIT_USERS` 2050-2052) via `populate_user_edit_data()`, NEVER `ADMIN_USER` (pk=1001) to avoid cross-test pollution.

### Two-adapter coexistence

- **`userAdapter`** (existing) owns identity + per-context MMR snapshots, populated by every list endpoint that ships a user. `UserEntry.nickname` / `.avatar` continue to be flattened by the backend (read from `BaseUserProfile`) so list views don't pay an extra fetch. **No breaking change.**
- **`userProfileEntityAdapter`** (new) owns the editable profile bundle, populated only on profile fetch (`GET /api/users/me/profile/`) or after a PATCH. Same `pk` key as `userAdapter` so consumers can join.

Lifecycle separation is the reason for two adapters rather than one. `userAdapter` is "cheap, populated everywhere"; `userProfileEntityAdapter` is "rich, populated only when the user views/edits their own profile."

### Edit modal

Replaces the current `frontend/app/pages/user/EditProfileModal.tsx` (207 lines, single flat form against `UpdateProfile`). The current modal is **brand-non-compliant** — it imports `Button` from `~/components/ui/button` and uses `variant="outline"` for Cancel. The rewrite explicitly does NOT inherit those violations.

**File organization (matches `frontend/app/components/events/EventSignupModal.tsx` + sibling `EventSignupModal/` dir convention; no `index.tsx`):**

- `frontend/app/pages/user/EditProfileModal.tsx` — modal entrypoint (top-level component, default export).
- `frontend/app/pages/user/EditProfileModal/` — sibling directory:
  - `schemas.ts` — Zod schemas.
  - `ProfileSkeleton.tsx` — Suspense fallback.
  - `ProfileErrorFallback.tsx` — ErrorBoundary fallback.
  - `tabs/BaseTab.tsx` — Base tab (T1).
  - (T2: `tabs/DotaTab.tsx`, `tabs/DeadlockTab.tsx`.)
  - (T3: `tabs/OrgTab.tsx`.)

**No `V2` suffix.** Atomic replacement: the new file overwrites `EditProfileModal.tsx` in the same PR that introduces the sibling directory.

**Tabs:** `Tabs` from shadcn (Radix-based) so ARIA roles (`role="tablist"`/`tab"`/`tabpanel"`) and keyboard nav are free.

- "Base" (always) + "Dota" + "Deadlock" (user-wide) + one tab per `OrgUser` the current user has (from `user.org_memberships`, ordered with `default_organization` first).
- Lazy-mounted tab content with per-tab `<Suspense>` inside each `<TabsContent>`.
- Each tab is an independent `useForm` instance + `useMutation` for the scoped PATCH. No shared mega-form.
- Each tab uses shadcn `Form` + `react-hook-form` + Zod (matching `2026-04-30-edit-user-modal-shadcn-form-migration-design.md`).
- `dirtyFields` checked per tab so we only PATCH what changed.
- Tabs grow additively across the three tickets.
- Many-orgs UX (scrolling tabs vs. vertical list vs. accordion) is deferred to T3. Default plan: vertical tab list with `default_organization` pinned first.

**Toast convention:** `sonner` (matches existing `EditProfileModal.tsx:5` and other modals). The repo has no `useMuiSnackbar` usage today; sonner is consistent. If a project-wide MUI conversion happens later, it's a separate cleanup ticket.

**Brand primitives — mandatory:**

- Cancel button: `<CancelButton>` (NOT `<Button variant="outline">`).
- Save button: `<SubmitButton loading={mutation.isPending}>`.
- Per-tab actions (verify MMR, upload screenshot): `<PrimaryButton>` / `<ConfirmButton>` / `<EditButton>` per the brand substitution table.
- Avatar preview (Base tab): `<UserAvatar user={...} size={...}>`. NEVER raw `<img>` or shadcn `<Avatar>`. Upload trigger: `<EditButton>` or `<PrimaryButton>` — never raw `<button>`.
- Per-org tab body header (T3): `<EntityBreadcrumb segments={[{type:'organization', label, href}]} currentLabel={user.nickname} />` — `EntityBreadcrumb` has no `user` segment type; using `organization` + `currentLabel` is the workaround (no schema change).
- **Forbidden:** raw `<button>`, `Button from '~/components/ui/button'` in any new tab file, `style={{}}` inline styles, hardcoded violet/slate hexes. Use `bg-base-*` scale + `cn()`.

**Frontend logger pattern:** the codebase has no `getLogger` helper. Match the existing convention — `console.debug/warn/error` with a bracket-prefix module tag:

```ts
const log = {
  debug: (...args: unknown[]) => console.debug('[user.editProfile.base]', ...args),
  warn:  (...args: unknown[]) => console.warn('[user.editProfile.base]', ...args),
  error: (...args: unknown[]) => console.error('[user.editProfile.base]', ...args),
};
```

PATCH failures also call `Sentry.captureException(err, { tags: { system: 'users', subsystem: 'profile' }, extra: { userPk } })`.

### Test infrastructure integration

DraftForge uses populate fixtures (`backend/tests/populate/`) and a feature-isolated user pool (`backend/tests/data/users.py`). The epic integrates as follows:

- **Backend tests** use `django.test.TestCase` (no `factory_boy` in the repo). Setup: call the relevant `populate_*_data()` helper and look up users by pk from `tests/data/users.py` (`ADMIN_USER`, `USER_EDIT_USERS[0]`, etc.).
- **Populate-fixture update (T1, mandatory task).** After T1, `backend/tests/populate/utils.py:53`, `backend/tests/populate/users.py:110-118`, and `backend/tests/populate/user_edit.py:117-124` (which today construct `CustomUser(nickname=..., ...)`) must EITHER:
  - (a) **Keep passing `nickname=` and `avatar=` to `CustomUser.objects.create()`** — backed by transitional setter properties on `CustomUser` that write through to `base_profile.nickname` / `base_profile.avatar`. The auto-create signal has already created the `BaseUserProfile` row by the time the setter fires. (RECOMMENDED — minimal call-site churn.)
  - (b) Update the populate helpers to write to `base_profile` after the user is saved.
  
  The setter property invalidates `BaseUserProfile` via `invalidate_after_commit`.
- **Playwright tests** use the existing `loginAdmin` / `loginAsUser` fixtures from `frontend/tests/playwright/fixtures/auth.ts:34+` (NOT a fabricated `authedPage`/`testUser` pattern).
- **Playwright selectors** use the existing `data-testid="edit-user-{field}"` convention from `frontend/tests/playwright/helpers/edit-user.ts:13-77`. The new modal MUST emit the same testids (`edit-user-nickname`, `edit-user-avatar`, `edit-user-btn`) so the existing `openEditModal` / `fillEditField` / `saveEditModal` helpers stay reusable.
- **Playwright test location:** rewrite the existing `frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts` to drive the new tabbed modal. No new `15-edit-profile/` directory.
- **Restore-in-test pattern** (NOT `afterEach`): read original → mutate → assert → restore. Per saved memory `feedback_no_flaky.md`, leaked state is a defect.
- **Auto-retrying assertions:** `expect(...).toHaveText(newNickname)` (10s default timeout from `playwright.config.ts:148-150`), NOT `getByText`. Eliminates the race between dual-write and assertion.
- **Feature-isolated populate data:** cacheops integration tests use `USER_EDIT_USERS` (pks 2050-2052) via `populate_user_edit_data()`. Never `ADMIN_USER` (pk=1001).

## Ticket breakdown

### T1 — BaseUserProfile end-to-end

**Backend:**
- **Existing Django app `user`** (already in `INSTALLED_APPS` as `user.apps.UserConfig` per commit `1ceeb9f9`). T1 extends it; does NOT create from scratch.
- New `BaseUserProfile` model in `backend/user/models.py` (OneToOne FK → `app.CustomUser`). Fields moved from `CustomUser`: `nickname`, `avatar`.
- Data migration: create one `BaseUserProfile` per existing `CustomUser`, copy `nickname` + `avatar` over, drop the columns from `CustomUser`. Migration calls `cache.clear()` at start and `invalidate_model(CustomUser); invalidate_model(BaseUserProfile)` at end. If `bulk_create`/`bulk_update` used, the post-bulk invalidations are mandatory.
- `CustomUser.save()` auto-creates `BaseUserProfile`.
- **Transitional setter properties** on `CustomUser` for `nickname` and `avatar`: getter returns `base_profile.<field>`, setter writes to `base_profile.<field>` and calls `invalidate_after_commit(base_profile)`. Keeps populate helpers and any incidental writers working without churn until removed in a cleanup ticket.
- New endpoints (registered under `backend/user/urls.py`): `GET /api/users/me/profile/`, `PATCH /api/users/me/profile/base/`. Both emit structlog logs as specified above.
- Serializers shipping user identity updated to read `nickname` / `avatar` from `base_profile`.
- Every `@cached_as(CustomUser, ...)` site shipping nickname/avatar updated to also depend on `BaseUserProfile`. Grep guardrail acceptance.
- `django-test-migrations` added: `poetry add --group dev django-test-migrations` then rebuild via `just test::setup`.

**Frontend:**
- `userProfileEntityAdapter` scaffolded in `userProfileStore.ts` with full type shape; only `base` layer wired.
- New `EditProfileModal.tsx` + sibling `EditProfileModal/` directory. Modal uses `<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery({ queryKey: ['userProfile', userPk], staleTime: 5min, gcTime: 10min })`. Write-through to Zustand via `useEffect` on `data` (NOT in `select`).
- Single "Base" tab editing nickname, avatar via shadcn `Form` + Zod + `useMutation`. `onSuccess` dual-writes to `userAdapter` AND calls `queryClient.invalidateQueries({ queryKey: ['userProfile', userPk] })`.
- Old `EditProfileModal.tsx` content replaced atomically.
- `frontend/app/routes/editProfile.tsx` and `UserProfilePage.tsx:20,181` updated to pass `userPk` (not the whole user object).

**Tests:**
- Backend: `backend/user/tests/test_models.py`, `test_auto_create.py`, `test_migration.py` (using `django-test-migrations`), `test_serializers.py`, `test_views.py`, `test_cacheops.py`, `test_transitional_setters.py`.
- Frontend (Vitest): `userProfileStore.test.ts` — adapter behavior, custom `hasChanged`, `reset()`.
- Playwright: rewrite `15-edit-user/06-profile-edit.spec.ts` to drive the new modal, using `loginAdmin` / `loginAsUser` fixtures, `data-testid` selectors, restore-in-test pattern, `expect(...).toHaveText(...)` for the dual-write assertion.

**Acceptance:**
- **Functional:** Logged-in user can open Edit Profile, change nickname or avatar, save, and see the change persist + reflect in every place a user-card is rendered. No regression in `userAdapter` consumers.
- **Brand:** `rg "from '~/components/ui/button'" frontend/app/pages/user/EditProfileModal/` returns zero hits. Cancel uses `<CancelButton>`, Save uses `<SubmitButton>`. Avatar preview renders via `<UserAvatar>`. No `style={{}}` or hardcoded violet/slate.
- **Cache:** `user.baseuserprofile` added to `CACHEOPS`. Grep guardrail `rg "@cached_as\(.*CustomUser" backend/app/ backend/user/ | rg -v "BaseUserProfile"` returns zero lines. Integration test mutates `BaseUserProfile.nickname` for a `USER_EDIT_USERS` user, hits a cached user-list view, asserts the change is reflected.
- **Frontend data flow:** Modal wraps `<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery` with `staleTime: 5min`. PATCH uses `useMutation`. `onSuccess` dual-writes to `userAdapter` AND calls `queryClient.invalidateQueries(['userProfile', userPk])`.
- **Logging:** Backend GET emits `profile_fetched` debug. PATCH emits `profile_base_patched` info with `fields_changed`. Validation errors emit `profile_base_patch_invalid` warning. Frontend uses bracket-prefix logger; PATCH failures call `Sentry.captureException` with `system`/`subsystem` tags.
- **Populate:** `backend/tests/populate/{utils.py,users.py,user_edit.py}` continue to work without call-site changes (transitional setter properties).
- **Playwright:** spec at `15-edit-user/06-profile-edit.spec.ts` uses `loginAdmin`/`loginAsUser` and `data-testid` selectors; restores any mutated nickname before test end; uses `expect.toHaveText` for dual-write assertion.

### T2 — DotaUserProfile + DeadlockUserProfile (user-wide) end-to-end

**Backend:**
- New models in `backend/user/models.py`: `DotaUserProfile` (OneToOne FK → `BaseUserProfile`; fields: `positions` FK to `PositionsModel` with default `related_name`, `has_active_dota_mmr`, `dota_mmr_last_verified`); `DeadlockUserProfile` (OneToOne FK → `BaseUserProfile`; fields mirror existing `PlayerDeadlockProfile`: `rank` loose string, `rank_date`).
- Data migration: create one `DotaUserProfile` per existing `BaseUserProfile`, move `CustomUser.positions` FK over, move `has_active_dota_mmr` + `dota_mmr_last_verified`, drop the columns. Bulk-write invariant applies (call `invalidate_model` after).
- `BaseUserProfile.save()` auto-creates `DotaUserProfile` and `DeadlockUserProfile` if missing.
- New endpoint: `PATCH /api/users/me/profile/game/{game}/` with structlog logging.
- **Backward-compat: `CustomUser.positions` read/write shim.** `@property` proxying to `dota_user_profile.positions` (getter) and writing to `dota_user_profile.positions` + `invalidate_after_commit(dota_user_profile)` (setter). Property removed in cleanup follow-up.
- `PositionsModel.save()` rewritten to walk `dotauserprofile_set` and `orgdotauserprofile_set` per the snippet above; logs each invalidation chain.
- Legacy `UpdateProfile` endpoint's positions path retired; nickname/avatar paths already moved in T1.

**Frontend:**
- `userProfileEntityAdapter` gains `gameUser.dota` and `gameUser.deadlock` layers.
- New `usePlayerPositions(userPk)` hook reading `gameTypeStore` + route context; pure `selectPositions(state, userPk, gameType, orgUserId?)` selector with primitive args.
- Modal gains lazy-loaded "Dota" and "Deadlock" tabs. Each tab is its own `useMutation` + `useForm`.
- Consumer migration: code reading `user.positions` directly (`rg "\.positions" frontend/app/`) switches to `usePlayerPositions(userPk)`. `userCacheTypes.ts` `UserEntry.positions` deprecated for one release, dropped in cleanup.

**Tests:** migration moves position FKs without data loss; `PositionsModel.save()` invalidation verified via cacheops integration test using `USER_EDIT_USERS`; endpoint perms; PATCH happy-path; Playwright extension in `15-edit-user/08-position-persistence.spec.ts`.

**Acceptance:**
- **Functional:** A user can edit user-wide Dota positions and Deadlock data via the modal. Existing position-display surfaces continue to work via the adapter. The `CustomUser.positions` shim (read + write) keeps unmigrated consumers working.
- **`related_name` discipline:** `rg "related_name=" backend/user/models.py` against the `positions` FKs shows either no `related_name` (default applies) OR explicit `related_name="dotauserprofile_set"` / `"orgdotauserprofile_set"`. Any other value fails CI.
- **Brand:** Dota and Deadlock tabs follow the same brand-primitive rules as Base.
- **Cache (blocker class):** `PositionsModel.save()` rewritten to invalidate `DotaUserProfile`, `OrgDotaUserProfile`, and their bubbled parents — NOT the now-empty `customuser_set`. `user.dotauserprofile` + `user.deadlockuserprofile` added to `CACHEOPS`. Auto-create inside `transaction.atomic()` uses `invalidate_after_commit`. Integration test mutates `PositionsModel` row, hits cached Dota draft view, asserts change reflected.
- **Frontend:** consumers reading `user.positions` migrated to `usePlayerPositions(userPk)`. Hook uses primitive selectors on `gameTypeStore` + `useShallow`.
- **Logging:** `PositionsModel.save()` emits `positions_invalidated` debug log with chain counts. New PATCH endpoint emits structured logs.

### T3 — OrgUserProfile + OrgDotaUserProfile / OrgDeadlockUserProfile end-to-end

**Backend:**
- New `OrgUserProfile` model (OneToOne FK → `OrgUser`, fields: none at launch).
- Rename `PlayerDotaProfile` → `OrgDotaUserProfile`, rewire FK from `OrgUser` → `OrgUserProfile`. Same for Deadlock. New positions FKs use default `related_name` (T2 constraint).
- Data migration: create one `OrgUserProfile` per existing `OrgUser`; rewire existing `PlayerDotaProfile` / `PlayerDeadlockProfile` rows to point at the new `OrgUserProfile`.
- `OrgUser.save()` auto-creates `OrgUserProfile`. Org-game profile auto-create on `OrgUserProfile.save()`.
- New endpoints: `PATCH /api/org-users/{org_user_pk}/profile/`, `PATCH /api/org-users/{org_user_pk}/profile/game/{game}/`. Structlog logging.
- `OrgUserSerializer` (`backend/org/serializers.py:9`) updated for layered shape.

**Frontend:**
- `userProfileEntityAdapter` `orgProfiles` layer wires up; `usePlayerPositions` prefers org override.
- Modal gains tabs for each `OrgUser` the current user has. Default UX: vertical tab list with `default_organization` pinned first.
- Per-org tab edits `OrgDotaUserProfile` via its own `useMutation`.

**Tests:** rename migration preserves rows; FK rewire reversible; endpoint perms; Playwright spec for "user is hard support in Org A, carry in Org B" using `USER_EDIT_USERS`.

**Acceptance:**
- **Functional:** A user in two organizations can set different position preferences for each, surfacing correctly in tournaments/drafts scoped to each org. User-wide Dota defaults unchanged.
- **Brand:** Per-org tab body header renders `<EntityBreadcrumb segments={[{type:'organization', label, href}]} currentLabel={user.nickname} />`. Tab list uses `bg-base-*` + `cn()`; no `style={{}}`; uses existing `ScrollArea` if scroll needed.
- **Cache:** CACHEOPS keys `org.playerdotaprofile` / `org.playerdeadlockprofile` renamed to `org.orgdotauserprofile` / `org.orgdeadlockuserprofile` in same PR as the model rename. `OrgUserProfile` deliberately NOT added to `CACHEOPS`. Integration test: user is support in Org A, carry in Org B; both org-scoped cached views reflect their respective positions.
- **Frontend:** `orgProfiles` layer wired; `usePlayerPositions` resolves org override → user-wide → undefined. Playwright spec covers the "support in Org A, carry in Org B" scenario end-to-end using `USER_EDIT_USERS`.

## Migration & rollback strategy

- **Each ticket revertible independently.** T1 doesn't touch positions; T2 doesn't touch org structure; T3 only touches org-side models.
- **Data migrations are forward-only with a tested down path.** Each Django migration ships a paired `reverse_code`. Tested against a production-data snapshot before each PR merges.
- **Cacheops disabled during migrations.** Migrations call `cache.clear()` at start and `invalidate_all()` at end.
- **Dual-write windows are short.** T1 transitional setters cover populate fixtures. T2's `CustomUser.positions` shim (read + write) covers unmigrated callers. T3 rename + rewire in a single migration.
- **Backward-compat surface:** `CustomUser.positions` property after T2 + `CustomUser.nickname`/`avatar` transitional setters after T1 are the shims. No API versioning needed; new endpoints are additive.

## Open questions

- **Deadlock user-wide fields.** Confirmed mirrors existing `PlayerDeadlockProfile` (`rank`, `rank_date`); confirm during T2 implementation if anything else belongs at the user-wide tier.
- **Many-orgs tab UX (T3 only).** Default = vertical tab list with `default_organization` first; decide during T3 implementation.
- **`CustomUser.positions` shim removal timing.** One full release after T2; cleanup ticket schedules removal once grep confirms no consumers remain.
- **`CustomUser.nickname` / `avatar` transitional setter removal.** Same pattern — one full release after T1, cleanup follow-up.
- **`guildNickname` placement.** Out of scope; stays on `CustomUser`. Follow-up could move to `OrgUserProfile`.
- **`immer` adoption.** Either add to `frontend/package.json` for nested writes or hand-spread like `userCacheStore.ts`. T1 implementation picks.

### Design calls made during multi-reviewer passes

- **Data loading: `<ErrorBoundary>` → `<Suspense>` → `useSuspenseQuery`.** TanStack Query already in use.
- **PATCH primitive: `useMutation`** (not `useActionState`). Integrates with `queryClient.invalidateQueries`. Idiomatic for React 19 + TanStack Query v5.
- **Write-through to Zustand:** `useEffect` on `data` (NOT inside `select`, which must be pure).
- **Cross-store coordination: pull model.** Hooks subscribe to both stores; React re-renders on either change. No `subscribeWithSelector` on `gameTypeStore`.
- **EntityBreadcrumb in T3 tabs:** `organization` segment + `currentLabel={user.nickname}` (no schema change to `EntityBreadcrumb`).
- **Toast library:** `sonner` (matches existing modal; no MUI snackbar in repo).
- **Models app:** new `users` Django app (long-term home for `CustomUser` too, via follow-up epic).
- **`@cached_as` enumeration:** explicit grep guardrail AC, not blanket "update all."
- **`CustomUser` transitional setters / `CustomUser.positions` shim:** both READ + WRITE through to the new owner with `invalidate_after_commit`. Avoids populate-fixture churn.

## Affected files (anchor list)

- **New Django app `backend/user/`** — `apps.py`, `models.py` (`BaseUserProfile`, `DotaUserProfile`, `DeadlockUserProfile`), `admin.py`, `serializers.py`, `views.py`, `urls.py`, `migrations/`, `tests/`. Added to `INSTALLED_APPS` in `backend/backend/settings.py`. Root URL conf wires `path("api/users/", include("user.urls"))`.
- `backend/backend/settings.py` — `INSTALLED_APPS` += `user.apps.UserConfig`; `CACHEOPS` += `user.baseuserprofile` (T1), `user.dotauserprofile` / `user.deadlockuserprofile` (T2), `org.orgdotauserprofile` / `org.orgdeadlockuserprofile` rename (T3).
- `backend/backend/urls.py` — include `user.urls`.
- `backend/app/models.py:92-140` — `CustomUser`: drop `nickname`/`avatar` columns + add transitional setter properties (T1); drop `positions` + MMR-verification columns + add property shim (T2); extend `save()` to auto-create `BaseUserProfile` (T1).
- `backend/app/models.py:48-53` — `PositionsModel.save()` rewrite (T2).
- `backend/app/migrations/00XX_drop_user_nickname_avatar.py` (T1), `00YY_drop_user_positions_mmr.py` (T2).
- `backend/app/serializers.py` — every user-identity serializer sources `nickname`/`avatar` from `base_profile` after T1.
- `backend/app/views_main.py` — every `@cached_as` site shipping nickname/avatar gains a `BaseUserProfile` dep (T1); every site shipping positions gains `DotaUserProfile`/`OrgDotaUserProfile` deps (T2).
- `backend/app/functions/tournament.py:456` — same `@cached_as` update.
- `backend/org/models.py` — `OrgUser` gets `OrgUserProfile` auto-create on save (T3).
- `backend/org/models_profiles.py` — `PlayerDotaProfile` / `PlayerDeadlockProfile` renamed + FK rewired in T3.
- `backend/org/serializers.py` — `OrgUserSerializer` (line 9) updated in T3 for layered shape.
- `backend/tests/populate/utils.py:53`, `backend/tests/populate/users.py:110-118`, `backend/tests/populate/user_edit.py:117-124` — work unchanged via transitional setters (T1) and property shim (T2).
- `pyproject.toml` — `[tool.poetry.group.dev.dependencies]` += `django-test-migrations`.
- `frontend/app/store/userCacheStore.ts` — no breaking change; flatten still works.
- New: `frontend/app/store/userProfileStore.ts`, `userProfileTypes.ts`, `userProfileStore.test.ts`.
- `frontend/app/components/api/userProfileApi.ts` — new client functions.
- `frontend/app/pages/user/EditProfileModal.tsx` — rewritten atomically (T1), tabs extended (T2, T3).
- `frontend/app/pages/user/EditProfileModal/` — new sibling directory with `schemas.ts`, `ProfileSkeleton.tsx`, `ProfileErrorFallback.tsx`, `tabs/BaseTab.tsx`, `tabs/DotaTab.tsx` (T2), `tabs/DeadlockTab.tsx` (T2), `tabs/OrgTab.tsx` (T3).
- `frontend/app/routes/editProfile.tsx` — mounts the new modal.
- `frontend/app/pages/user/UserProfilePage.tsx:20,181` — passes `userPk` to the new modal.
- All consumers of `user.positions` in `frontend/app/components/` — migrated to `usePlayerPositions` in T2.
- `frontend/tests/playwright/e2e/15-edit-user/06-profile-edit.spec.ts` — rewritten to drive new modal (T1). `08-position-persistence.spec.ts` extended for T2. `10-cache-merge.spec.ts` verified compatible.

## Related issues

- [#224](https://github.com/kettleofketchup/DraftForge/issues/224) — original feature ticket, to be rewritten as the epic.
- [#202](https://github.com/kettleofketchup/DraftForge/issues/202) — broader game-scoping problem; this epic unblocks it.
- `2026-04-30-edit-user-modal-shadcn-form-migration-design.md` — sibling form-migration work; the new modal follows the same shadcn Form + Zod pattern.
