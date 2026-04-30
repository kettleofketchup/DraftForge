# Edit User Modal — shadcn Form migration + scope-aware permissions

**Date:** 2026-04-30
**Status:** Draft (spec); awaiting user review
**Owner:** Mark Paxson
**Branch:** TBD (will branch from `main`)

## Summary

Migrate `frontend/app/components/user/userCard/{editModal.tsx, editForm.tsx, handleSaveHook.tsx}` from the legacy hand-rolled `useState` form to the shadcn `Form` + `react-hook-form` + Zod pattern already used by `EditLeagueModal`, `EditEventModal`, and seven other modals in the codebase. Add a `scope` discriminated-union prop so the same modal works correctly when rendered from org / league / global / tournament-error contexts, with scope-aware permissions and MMR field visibility.

The migration eliminates three latent bugs that cause "sticky" values when admins edit multiple users in sequence: an `onFocus` handler that clobbers user edits, uncontrolled position `<Select>` components whose internal state diverges from form state, and a `setForm({})` reset that races a re-seeding `useEffect`.

## Motivation

Admins editing users on org pages report that fields silently revert to their previous values when they edit a second user after a first. Reproduction: open user A's modal, change MMR, save; open user B's modal, change MMR, save; reopen user A — A's MMR change is gone (or B's is, or a position dropdown shows the wrong value).

Investigation found three root causes in the legacy form:

1. **`onFocus={() => handleChange(key, user[key])}`** in `editForm.tsx:102` — every time the user focuses an input, the form value is overwritten with the original. Tab away and tab back and your edit is gone.
2. **Uncontrolled position `<Select>`** in `editForm.tsx:135-217` — no `value` prop, current value is faked via `placeholder`. The dropdown's internal state diverges from `form.positions` once touched.
3. **`setForm({})`** in `handleSaveHook.tsx:82` — blanks the form on save success, which races the parent's `useEffect` re-seeder watching `[user]` and `[user.pk]`.

Beyond the bug fix, the modal's permission gate is wrong: it hard-codes `currentUser.is_staff || currentUser.is_superuser`, which locks out non-Django-staff org admins who legitimately can edit their members. The modal is rendered in four distinct contexts, each with different permission semantics and different MMR semantics.

## Non-goals

- **No backend changes.** `updateOrgUser` already accepts `Partial<UserType>`; we use it as-is. A future `PATCH /leagues/:id/users/:pk/` endpoint can be added later without changing this spec's frontend code (only `useEditUserMutation`'s league branch needs to swap one call).
- **No `PlayerModal` rewrite.** `PlayerModal.tsx` consumes `UserEditModal` and gets the migration's benefits transparently. It will gain a `scope` prop pass-through; it is not otherwise touched.
- **No new editable fields.** The current set (`nickname`, `mmr`, `steam_account_id`, `guildNickname`, `positions`) is preserved. `is_staff` and `is_superuser` remain non-editable in this UI.
- **No selector changes.** Existing `data-testid="edit-user-{field}"` IDs are preserved so the 6 specs in `tests/playwright/e2e/15-edit-user/` and the helpers in `tests/playwright/helpers/edit-user.ts` keep passing without modification.
- **No bulk edit.** One user at a time, as today.

## Architecture

### Modal API

```ts
type EditUserScope =
  | { kind: 'org';    organization: OrganizationType }
  | { kind: 'league'; league: LeagueType; organization?: OrganizationType }
  | { kind: 'global' };

interface UserEditModalProps {
  user: UserClassType;
  scope: EditUserScope;
  /** Optional per-field visibility override; defaults are sensible per scope. */
  fields?: Partial<Record<EditableField, boolean>>;
}
```

`scope` drives three things: the permission check that gates the trigger button, the MMR field's visibility and label, and the API endpoint the PATCH is routed to.

### Permission resolution

Computed via existing `usePermissions.ts` hooks — no new permission logic.

| `scope.kind` | Trigger button renders if |
|---|---|
| `org` | `useIsOrganizationStaff(scope.organization)` |
| `league` | `useIsLeagueAdmin(scope.league, scope.organization)` |
| `global` | `useIsSuperuser()` |

If the check fails, `<UserEditModal>` returns `null` — same pattern as today, just gated correctly per context.

A small wrapper hook `useScopedEditPermission(scope)` lives in the modal file and dispatches to the right underlying hook.

### MMR semantics per scope

| Scope | MMR field shown? | Label | Source on open | PATCH endpoint |
|---|---|---|---|---|
| `org` | yes | "Org MMR" | `user.mmr` (caller already swaps to `orgEntry.mmr`) | `/organizations/:orgPk/users/:orgUserPk/` |
| `league` | yes | "MMR" | `user.mmr` (today; `user.league_mmr` once a league endpoint exists) | `/organizations/:orgPk/users/:orgUserPk/` (today, via parent org) |
| `global` | **no** | — | — | `/users/:pk/` |

Hiding MMR in global scope is deliberate: a superuser viewing a profile page (no org/league context) shouldn't be able to globally bump a user's MMR — that's a footgun affecting every org. MMR is org/league-scoped only. Other fields (`nickname`, `steam_account_id`, `guildNickname`, `positions`) are user-global in all scopes and PATCH cleanly to any of the three endpoints.

The `fields` prop allows callers to override defaults if needed (e.g., hide MMR explicitly in org scope). Default behavior matches the table above.

### File layout

```
frontend/app/components/user/userCard/
  editModal.tsx           ← FormDialog shell + permission gate + scope-routed PATCH (~80 lines, was 130)
  editForm.tsx            ← FormField-driven body, controlled inputs (~120 lines, was 253)
  editUserSchema.ts       ← NEW. Zod schema + EditUserInput + buildDefaults(user, scope) + pickDirty helper
  handleSaveHook.tsx      ← DELETED. Save logic inlined into editModal's onSubmit.
```

The `useEditUserMutation` hook proposed in earlier drafts has been **removed**. The mutation logic is short enough (≤25 lines) to inline directly in `onSubmit`, matching `EditLeagueModal`'s convention. Introducing a third pattern (custom `useCallback` hook) for one consumer doesn't pay for itself.

### Zod schema (`editUserSchema.ts`)

```ts
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
  mmr: z.coerce.number().int().min(0).nullable().optional(),  // optional → omitted in global scope
});

export type EditUserInput = z.infer<typeof EditUserSchema>;

export function buildDefaults(user: UserClassType, scope: EditUserScope): EditUserInput {
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
  };
  return scope.kind === 'global' ? base : { ...base, mmr: user.mmr ?? null };
}
```

`z.coerce.number()` solves the `<Input type="number">`-gives-string problem cleanly. `.nullable()` on string fields handles users with no nickname yet. Validation errors flow per-field through `<FormMessage />`.

### Modal shell (`editModal.tsx`)

Uses `<FormDialog>` from `~/components/ui/dialogs` (the established convention used by `EditLeagueModal` and `EditEventModal`) — not a hand-rolled `<Dialog>`. `FormDialog` bundles header/title/description/footer, mobile-full-screen sizing, scroll, the brand Cancel/Submit buttons with loading spinner, and `onPointerDownOutside`/`onInteractOutside` guards that prevent accidental dismiss. Re-implementing those by hand loses the outside-click guard plus the standard `modal-cancel-button` / `form-dialog-submit` test IDs.

The mutation logic is inlined; no external hook. The earlier-draft `useEditUserMutation` and the legacy `handleSaveHook.tsx` are both gone.

```tsx
export function UserEditModal({ user, scope, fields }: UserEditModalProps) {
  const canEdit = useScopedEditPermission(scope);
  const [open, setOpen] = useState(false);
  const showMmr = scope.kind !== 'global' && (fields?.mmr ?? true);

  const form = useForm<EditUserInput>({
    resolver: zodResolver(EditUserSchema),
    defaultValues: buildDefaults(user, scope),
  });

  // Re-seed when modal opens or the underlying user changes.
  // Deps are narrowed to identity keys (not the scope object literal) to
  // avoid re-firing on every parent render. Cross-entity transitions within
  // the same scope.kind (e.g. switching the modal target from org A to
  // org B without scope.kind changing) are covered by the `open` toggle:
  // the modal must close between users, so the next open re-runs reset
  // with the new user/scope. Caller-side `useMemo` of scope is recommended
  // for stability but not required by this effect.
  useEffect(() => {
    if (open) form.reset(buildDefaults(user, scope));
  }, [open, user.pk, user.orgUserPk, scope.kind, form]);

  async function onSubmit(data: EditUserInput) {
    if (!form.formState.isDirty) {
      // No changes — close without firing PATCH (avoids the backend's
      // "No valid fields to update" 400 from update_org_user).
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
      const message = err instanceof Error ? err.message : `Failed to update ${user.username}`;
      toast.error(message);
    }
  }

  if (!canEdit) return null;

  return (
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
  );
}
```

`dispatchPatch` and `scopeToContext` are local helpers in the same file (or co-located in `editUserSchema.ts`):

```ts
async function dispatchPatch(user: UserClassType, scope: EditUserScope, payload: Partial<EditUserInput>) {
  if (scope.kind === 'org') {
    if (!user.orgUserPk) throw new Error('Org scope requires user.orgUserPk');
    return updateOrgUser(scope.organization.pk, user.orgUserPk, payload);
  }
  if (scope.kind === 'league') {
    // FLEXIBLE POINT: today routes through the parent org's OrgUser endpoint.
    // When a league-user PATCH endpoint lands, swap this branch to call
    // updateLeagueUser(scope.league.pk, user.orgUserPk, payload).
    const orgId = scope.organization?.pk ?? scope.league.organization?.pk;
    if (!orgId || !user.orgUserPk) {
      throw new Error('League scope requires a parent org with an OrgUser link');
    }
    return updateOrgUser(orgId, user.orgUserPk, payload);
  }
  if (!user.pk) throw new Error('Global scope requires user.pk');
  return user.dbUpdate(payload);
}

function scopeToContext(scope: EditUserScope) {
  if (scope.kind === 'org')    return { orgId: scope.organization.pk };
  if (scope.kind === 'league') return { orgId: scope.organization?.pk ?? scope.league.organization?.pk };
  return undefined;
}
```

**Notes on this shape (consolidated from review):**

- **No `memo()` wrapper.** Reference modals (`EditLeagueModal`, `EditEventModal`) don't use it; React Compiler handles re-render minimization, and RHF's `Controller`/`FormField` already isolate field re-renders. The legacy `memo()` is dropped.
- **`form.formState.isSubmitting` over redundant `useState`.** This is intentional and improves on both reference modals (which keep a parallel `useState` flag).
- **Trigger is rendered as a sibling controlled by the `open` state.** `FormDialog` does not expose a `trigger` prop — confirmed by reading `frontend/app/components/ui/dialogs/FormDialog.tsx`. The `<EditIconButton>` with `data-testid="edit-user-btn"` lives outside the `<FormDialog>` and calls `setOpen(true)`. Implementation must verify `<EditIconButton>` is a brand-canonical wrapper (preferably built on `<EditButton>` which is the documented purple + 3D edit affordance per `docs/THEMING-GUIDE.md`) and not a daisyUI relic — if it is, swap to `<EditButton>` in the same PR.
- **`FormDialog` brand inheritance.** `FormDialog` wraps shadcn `<Dialog>`/`<DialogContent>`, so it inherits `brandBg` automatically. Its submit button is a `<SubmitButton>` (gradient + 3D per the theming guide) and its cancel button is a `<CancelButton>` — do not pass these manually, and do not bypass them with shadcn `<Button>` directly.
- **Empty-PATCH guard** is the `formState.isDirty` early return. Without this, the org backend at `admin_team.py:768-771` returns 400 for an empty body. The earlier draft incorrectly claimed empty PATCH would 200; this is the fix.

### Form body (`editForm.tsx`)

Each input becomes a `<FormField control={form.control} name="…" render={({field}) => …} />`. Position selects are genuinely controlled and wrapped in `<FormControl>` for proper aria-wiring (matches `EditEventModal:235-249`):

```tsx
<FormField
  control={form.control}
  name="positions.carry"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Carry</FormLabel>
      <Select
        value={String(field.value)}
        onValueChange={(v) => field.onChange(parseInt(v, 10))}
      >
        <FormControl>
          <SelectTrigger data-testid="edit-user-carry">
            <SelectValue placeholder="Select" />
          </SelectTrigger>
        </FormControl>
        <SelectContent>
          <SelectItem value="0">0: Don't show this role</SelectItem>
          <SelectItem value="1">1: Favorite</SelectItem>
          <SelectItem value="2">2: Can play</SelectItem>
          <SelectItem value="3">3: If the team needs</SelectItem>
          <SelectItem value="4">4: I would rather not but I guess</SelectItem>
          <SelectItem value="5">5: Least Favorite</SelectItem>
        </SelectContent>
      </Select>
      <FormMessage />
    </FormItem>
  )}
/>
```

The `value={String(field.value)}` makes the trigger reflect form state at all times — no more placeholder hack (the `placeholder="Select"` on `<SelectValue>` is just a defensive fallback for users with malformed data; `buildDefaults` guarantees non-undefined values for normal cases). The five position selects are extracted into a small `<PositionSelectGrid>` component to keep `editForm.tsx` readable.

**Test ID placement:** `data-testid="edit-user-{field}"` IDs go on the leaf input element — `<Input>` for text/number fields, `<SelectTrigger>` for selects. Not on `<FormItem>` or `<FormControl>`. This matches `EditLeagueModal.tsx:100`.

The MMR `<FormField>` is rendered conditionally on `showMmr`.

### Caller updates

| File | Change |
|---|---|
| `userCard.tsx:203` | `const scope = useMemo(() => orgEntry ? { kind: 'org', organization: currentOrg } : { kind: 'global' }, [orgEntry?.id, currentOrg?.pk]);` then `<UserEditModal user={...} scope={scope} />`. The `useMemo` stabilizes the object identity — without it, the modal's seed-on-open `useEffect` would re-fire on every parent render. |
| `pages/tournament/hasErrors.tsx:104` | Same pattern: `useMemo` the scope literal. `<UserEditModal user={user} scope={scope} />` |
| `player/PlayerModal.tsx:150` | Read scope from existing `PlayerModalContext` (from `shared-popover-context.tsx:22-25`, fields `leagueId?` and `organizationId?`). Resolve numeric IDs to entities via `useUserCacheStore` / org+league stores. If `organizationId` present → org scope; if `leagueId` present → league scope (org lookup via `league.organization`); else → global. |

`userCard.tsx` already has access to `currentOrg` via `useOrgStore`. `hasErrors.tsx` already receives `league` and can derive `organization` from `league.organization` or pull from store. `PlayerModal` already accepts a `PlayerModalContext` argument via `openPlayerModal(player, context)` — that context is currently unused by `UserEditModal`. This migration wires it up. Existing `openPlayerModal(player)` call sites without context (e.g. `PlayerPopoverTrigger.tsx`, `shared-popover-renderer.tsx`, `userCard.tsx:43`) default to global scope, which means non-superusers stop seeing the edit button on those popovers — this matches the spec's scope-aware safety property. Call sites that should keep edit access (org/league pages opening the popover) get an `openPlayerModal(player, { organizationId })` or `{ leagueId }` update; the implementation plan enumerates these.

### Bug → fix mapping

| Bug (today) | Fix (after migration) |
|---|---|
| `onFocus` reverts edits on tab-back | Removed entirely. RHF's `field.onChange` is the only writer to form state. |
| Uncontrolled `<Select>` drifts from form | `value={String(field.value)}` makes selects controlled. |
| `setForm({})` race on save success | Gone. RHF's `form.reset(newDefaults)` runs from `useEffect` on user/open change, no manual blanking. |
| Hard-coded `is_staff` permission gate | `useScopedEditPermission(scope)` dispatches to the right hook per scope. |
| MMR shown to superusers in global scope (footgun) | `showMmr = scope.kind !== 'global'` hides the field. |
| Full-form PATCH overwrites concurrent edits | `pickDirty(data, dirtyFields)` sends only changed fields. |
| Empty PATCH (open + save without changes) → backend 400 | `formState.isDirty` early return in `onSubmit` skips the request. |
| Cargo-culted `memo()` wrapper | Removed. References don't use it; React Compiler / RHF handle re-renders. |
| `<Select>` missing `<FormControl>` wrapper (no aria-invalid wiring) | Wrapped in `<FormControl>` per `EditEventModal:235-249` convention. |

## Theming and visual parity

The legacy `editForm.tsx` mixes daisyUI utility classes (`input input-bordered`, `select select-bordered`, `card-compact bg-base-300`, `form-control`, `label`, `input-error`) with raw Tailwind colors (`bg-gray-800`). The migration **drops all of these** and follows `docs/THEMING-GUIDE.md` tokens — shadcn primitives already self-style; appending daisyUI fights the theme.

| Surface | Token / class |
|---|---|
| Position panel container | `bg-base-300 border border-border rounded-lg p-4` (replaces `bg-gray-800 shadow-md p-4 rounded-lg hover:shadow-lg hover:shadow-gray-500/50`) |
| Position grid layout | `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4` (replaces malformed `flex flex-col md:flex-row md:cols-2 xl:cols-3` — `md:cols-2` and `xl:cols-3` are **invalid Tailwind utilities** and the responsive breakpoints don't actually fire today) |
| Field labels | `<FormLabel>` only — drop manual `font-semibold` overrides; the component already styles itself |
| Helper / placeholder text | `text-muted-foreground` (no raw gray classes) |
| Error text | `<FormMessage>` (resolves to `text-destructive` per shadcn) — no `text-error` daisyUI class |
| Focus rings | Inherited from shadcn `<Input>` / `<SelectTrigger>` (uses `--ring`) — do NOT add `input-bordered` which conflicts |
| Submit / Cancel buttons | Provided by `<FormDialog>` — do not pass `<SubmitButton>` / `<CancelButton>` manually |

**Forbidden classes in the new form** (carried-forward technical debt — explicitly listed so reviewers can grep):

- Raw color utilities: `bg-gray-800`, `bg-gray-900`, any `slate-*` / `gray-*` tokens, manual `bg-base-300` overrides on shadcn primitives.
- daisyUI form tokens: bare `input`, `input input-bordered`, `input-error`, bare `select`, `select select-bordered`, `form-control`, daisyUI `label` (use `<FormLabel>`), `card-compact`.
- Bogus / non-Tailwind classes from the legacy file: `align-center`, `align-middle` on flex/grid containers (these are not real Tailwind utilities), `md:cols-2`, `xl:cols-3` (use `md:grid-cols-N` / `xl:grid-cols-N` on a `grid` parent), trailing/duplicated `w-full`.
- Inline overrides on shadcn components: manual `font-semibold` on `<Label>` / `<FormLabel>` (the component already styles itself); `text-error` *as a form-state class* is forbidden — use `<FormMessage>` instead. `text-error` for non-form inline text is acceptable per `THEMING-GUIDE.md`.

The trigger button (`<EditIconButton>` with `data-testid="edit-user-btn"`) is unchanged — already inherits brand styling. The dialog title tone (`Edit {nickname || username}` / `Update this user's profile.`) matches `EditLeagueModal`'s register; no change needed.

Visual smoke check is part of the manual-verification list under Testing.

## Display vs. submit

To address an explicit concern raised during brainstorming: the modal still **displays** every current field value, populated from `buildDefaults(user, scope)`. Users see what they always saw. The "dirty fields only" change is purely about the **PATCH body**.

| Aspect | Behavior |
|---|---|
| Modal opens | All fields populated with current values via `form.reset(buildDefaults(user, scope))` |
| User edits one field, saves | PATCH body contains only that one field |
| User edits no fields, saves | Client-side guard via `formState.isDirty` skips the request and closes the dialog (avoids the org backend's 400 at `admin_team.py:768-771`) |
| Concurrent edit by another admin | The other admin's untouched fields survive (key safety property) |

## Backend response shapes

The two PATCH paths return structurally different payloads. This is pre-existing behavior, but the spec must acknowledge it because the frontend `useUserCacheStore.upsert` consumes both:

| Endpoint | Returned serializer | Includes |
|---|---|---|
| `PATCH /organizations/:orgPk/users/:orgUserPk/` | `OrgUserSerializer` | slim: org-scoped fields, no `email` / `is_staff` / `is_superuser` / `discordId` |
| `PATCH /users/:pk/` | `UserSerializer` | full user record |

`useUserCacheStore.upsert` in `frontend/app/store/userCacheStore.ts:151` already does its own merge loop using `toUserEntry(raw, context, existing)` and explicitly bypasses the adapter's `upsertMany` precisely to handle scope-divergent payloads (see comment at line 146-150). The merge is safe because `pick()` in that file (lines 22-33) only copies keys that satisfy `key in obj` — fields *absent* from the slim `OrgUserSerializer` payload (e.g. `email`, `is_staff`, `is_superuser`, `discordId`) are not copied, so existing values survive. **No change needed in the cache store**, but the implementation plan adds `10-cache-merge.spec.ts` to pin the behavior — guards against a future serializer change adding `email: null` (which *would* overwrite).

### Server-side cache invalidation

Two backend invalidation paths matter:

| PATCH path | Invalidation today | Status |
|---|---|---|
| `update_org_user` (org scope) | Calls `invalidate_after_commit(org_user, org, *user.tournaments, *league_users, *(lu.league for lu in league_users))` at `admin_team.py:773-789`. | ✅ Org/league user lists invalidate correctly. |
| `UserSerializer.update` (global scope) | Cacheops auto-invalidates on `CustomUser.save()`, but `@cached_as(OrgUser, ...)` views keyed on related `OrgUser` rows only invalidate if `OrgUser` is in the cache key deps. | ⚠️ Verify during implementation. If global edits to `nickname` / `positions` / `steam_account_id` leave org-page lists stale until 1h TTL, harden by adding an equivalent `invalidate_after_commit` for related `OrgUser` rows in `UserSerializer.update`, or by ensuring the relevant `cached_as` decorators include `CustomUser` in their model deps. |

The implementation plan must include a verification step (Django shell: edit a user globally, then GET an org user list endpoint, confirm the change appears immediately) before the PR is merged. If verification reveals stale caches, the fix lands in this PR.

## Testing

All new tests are Playwright E2E specs under `frontend/tests/playwright/e2e/15-edit-user/`. The 6 existing specs (`01-org-edit.spec.ts` through `06-profile-edit.spec.ts`) keep passing without changes — selectors and helpers are preserved.

### `07-sequential-multi-user.spec.ts` (NEW) — the regression test

This is the test the existing 6 specs don't cover and the reason the bug shipped.

```
@cicd test: edit user A then user B sequentially; both saves persist
  1. Visit org page, switch to Users tab.
  2. Open user A's modal → change nickname + MMR + carry position → save.
  3. Reload page (or re-fetch users list).
  4. Open user B's modal → change nickname + MMR + soft_support position → save.
  5. Reload page.
  6. Re-open user A's modal → assert all 3 of A's fields show the new values.
  7. Re-open user B's modal → assert all 3 of B's fields show the new values.
  8. Restore originals.
```

Also intercepts the PATCH and asserts the body contains only the changed keys (pins dirty-only behavior):

```ts
const body = JSON.parse((await patchPromise).postData()!);
expect(Object.keys(body).sort()).toEqual(['mmr', 'nickname', 'positions']);
```

### `08-position-persistence.spec.ts` (NEW) — controlled-Select regression test

```
@cicd test: position dropdown changes persist correctly
  1. Open modal for a known user.
  2. Change carry from current → "1: Favorite" via dropdown.
  3. Change hard_support from current → "5: Least Favorite".
  4. Save; intercept PATCH; assert body.positions.carry === 1 and .hard_support === 5.
  5. Re-open modal; assert dropdown triggers display the new values (not placeholder).
```

Adds a small helper `readPositionField(page, position)` to `helpers/edit-user.ts` that reads the rendered `SelectTrigger` text (existing `readEditField` only reads `<input>` values).

### `09-scope-permissions.spec.ts` (NEW)

Three sub-tests:

```
test: org admin (non-superuser) sees edit-user-btn on org page
test: org admin does NOT see edit-user-btn on user profile page (global scope)
test: superuser on profile page does not see edit-user-mmr field in DOM
```

Requires a populate fixture for a non-superuser org admin. If `populate_users.py` (or equivalent) doesn't already create one, a small populate addition is part of the implementation plan.

### Existing specs

The 6 existing specs in `15-edit-user/` will be re-run after migration. None should require selector changes. If any depend on full-form PATCH semantics (worth a `grep "request().postData()"` pass), they'll be updated to match dirty-only semantics.

### Backend tests (added in this PR)

Two Django tests pin the partial-PATCH semantics on which the frontend relies. Run via `just test::run 'python manage.py test app.tests.test_user_partial_patch -v 2'`.

1. **`test_partial_positions_patch_does_not_zero_other_slots`** — `PATCH /organizations/:org/users/:orgUser/ {"positions": {"carry": 1}}` must leave `mid`, `offlane`, `soft_support`, `hard_support` at their previous values. Pins `update_org_user:754-765`'s nested-iter behavior.
2. **`test_global_partial_positions_patch_passes_serializer_validation`** — `PATCH /users/:pk/ {"positions": {"carry": 3}}` must return 200 (not 400 from `PositionsSerializer` field-required validation). The Django reviewer flagged that `PositionsSerializer` (`serializers.py:48-58`) declares all five fields without `required=False`; with `partial=True`, DRF *should* tolerate this, but it's worth pinning so a future serializer change doesn't silently break partial position edits.

If either test reveals an actual backend bug (e.g., test 2 fails), the fix lands in this same PR — adding `required=False` to the nested fields, or marking `PositionsSerializer` itself as `partial=True`. The frontend changes ride on the assumption that partial position PATCH works on both endpoints.

### Frontend cache merge test

`tests/playwright/e2e/15-edit-user/10-cache-merge.spec.ts` (NEW): after editing a user via the org-scoped modal, verify the user card on a non-org page (e.g., user profile) still shows `is_staff` / `email` / `discordId`. Catches a regression where `useUserCacheStore.upsert` would replace rather than merge after the slim `OrgUserSerializer` response.

### Manual verification

Documented as a checklist for the implementer to run on a dev environment after migration:

- [ ] Open the modal in each scope (org page, league page, tournament errors panel, profile page) — verify the right fields render, the right MMR label appears or doesn't.
- [ ] Open DevTools Network tab; edit one field; confirm PATCH body contains only that field.
- [ ] Edit two users in sequence; confirm both persist after page reload.
- [ ] Visual smoke: modal looks identical to today — same widths, same spacing, same scroll behavior in `DIALOG_CSS_SMALL`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Selector drift breaks existing E2E specs | All `data-testid` IDs preserved. CI runs the full `15-edit-user/` suite as a gate. |
| `PlayerModal` popover loses edit button on org/league pages where it currently appears | The migration enumerates each `openPlayerModal` callsite. Org/league page callers get a `{ organizationId }` or `{ leagueId }` context arg added in the same PR. CI runs the new `09-scope-permissions.spec.ts` plus a smoke test that opens a popover from an org page and confirms the edit button still appears for org admins. |
| Concurrent-edit safety regresses | `07-sequential-multi-user.spec.ts` pins dirty-only PATCH behavior. |
| `is_staff` users on org pages lose access who currently have it | Unlikely — `is_staff` Django flag implies superuser-like access in this codebase, and `useIsOrganizationStaff` short-circuits to true for `is_staff`. Verified by `useIsOrganizationAdmin:69` (`if (currentUser.is_staff) return true;`). |
| Position select layout regresses (5-column grid) | New grid uses `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4` (the legacy `md:cols-2 xl:cols-3` was invalid Tailwind that didn't actually fire — visual fix, not regression). Smoke step in manual verification covers it. |
| Cache store merges scope-divergent payloads incorrectly, dropping fields | `useUserCacheStore.upsert` already bypasses the adapter's `upsertMany` and merges via `toUserEntry` (`userCacheStore.ts:146-178`). The new `10-cache-merge.spec.ts` pins the behavior. |
| Empty-PATCH client guard regression (someone removes the `isDirty` check) | `07-sequential-multi-user.spec.ts` includes a sub-step that opens the modal, immediately clicks Save, and asserts no PATCH request fired. |
| `FormDialog` migration loses `data-testid="edit-user-btn"` on the trigger | Trigger remains a separate `<EditIconButton>` wired to the dialog's `open` state — not an internal `FormDialog` slot. Verified by re-running `01-org-edit.spec.ts` which clicks `edit-user-btn`. |
| Global `/users/:pk/` PATCH leaves org-page user list caches stale until TTL | Verified during implementation per the "Server-side cache invalidation" section. If stale, fix by adding `invalidate_after_commit` for related `OrgUser` rows in `UserSerializer.update`. |

## Out of scope (for a follow-up)

- Migrating `PlayerModal.tsx` to the same pattern (its internal `useState` form has its own quirks but isn't the source of the reported bug).
- Adding a real `PATCH /leagues/:id/users/:pk/` backend endpoint and switching the league scope to use it.
- Editing `is_staff` / `is_superuser` flags from this modal.
- Bulk-edit affordances.
- Introducing the **Component-First wrapper convention** (`components/custom/AppInput`, `components/custom/AppSelect`, etc.) referenced in the global instructions. The codebase doesn't follow this pattern today — `EditLeagueModal` and `EditEventModal` import shadcn primitives directly. Adding wrappers in this PR would create inconsistency. If the team adopts component-first wrappers later, the user modal can be migrated alongside.
