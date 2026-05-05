# Event Signup Form — Design Spec

**Date:** 2026-05-05
**Status:** Draft (pending implementation plan)
**Branch (when implemented):** `feat/event-signup-form`

## Context

Today, signing up for an event has two surfaces with very different fidelity:

- **Discord** — clicking the green **Sign Up** button on an event embed opens a rich, multi-step flow that collects Steam Friend ID, preferred Dota 2 positions, rank status (active / previous / never), medal + star or Battle Cup tier, and (when the event requires it) an MMR or Battle Cup screenshot. Profile data is persisted to the user's `PlayerDotaProfile` and reused on the next event. Implementation lives in `backend/discordbot/components.py` and `backend/events/discord/handlers.py`.
- **Website** — clicking **Sign Up** on `/events/<id>` opens a single confirm dialog ("RSVP for Event?") and fires `POST /api/events/<id>/rsvp/`. No data collection. Admins fill in the player's MMR after the fact via the existing `MmrApprovalModal`.

The asymmetry is a real product problem: web users skip the data-gathering step that Discord users go through, which means the admin approval queue carries unequal load and per-event signup-policy flags (`min_mmr`, `discord_require_rank_screenshot`, etc.) are effectively unenforced for web signups. This spec brings the website to data parity with Discord.

## Field-name reference (load-bearing)

The `Event` model uses **mixed naming** — the `discord_` prefix is not consistent across config flags. Spec language and code references must match exactly:

| Field on `Event`                         | Notes                                                |
| ---------------------------------------- | ---------------------------------------------------- |
| `require_steam_id`                       | **No `discord_` prefix.** Friend ID gate.            |
| `allow_active_mmr`                       | No prefix.                                           |
| `allow_previous_rank`                    | No prefix.                                           |
| `allow_battlecup_rating`                 | No prefix.                                           |
| `min_mmr`                                | No prefix. Floor enforced by `process_rsvp`.         |
| `discord_require_rank_screenshot`        | **Has** `discord_` prefix.                           |
| `discord_require_battlecup_screenshot`   | **Has** `discord_` prefix.                           |

Implementers must verify any new code references against `backend/events/models.py` rather than copying from the spec, since the prefix asymmetry is easy to get wrong.

## Goals

- Web signup collects the same player data Discord collects, gated by the same per-event flags listed above.
- A web-initiated signup ends up in the database **indistinguishable** from a Discord-initiated one — same `EventSignup`, same `PlayerDotaProfile` writes, same downstream admin flow, same `process_rsvp` business logic, same `notify_signup_changed` Discord-embed refresh.
- Repeat web signups respect the user's prior profile data: nothing-missing-no-form fast path mirrors Discord's instant signup.
- Both **Sign Up** and **Tentative** buttons use the same form; only the resulting `EventSignup.status` and submit-button label differ.
- A single canonical signup-input service is shared between Discord and web — no duplicated business logic.
- Brand-compliant per `docs/THEMING-GUIDE.md` (brand button system including `<SubmitButton>` / `<CancelButton>` for form modals; `bg-base-*`; no raw `<button>`).

## Non-goals

- **Deadlock.** The Discord modal supports a Deadlock variant (free-text rank + last-played date). The Friend ID gate applies to all game types, but the rich Dota 2 form (positions, rank-status branch, medal/star/Battle Cup, screenshot) is **not** mirrored for Deadlock in this iteration. Deadlock signups continue through Discord.
- **File upload pipeline.** The codebase has no `MEDIA_ROOT`, `STORAGES`, or S3 client. Screenshots are URL-paste only (imgur or any `https?://…`), matching Discord's existing fallback. A real upload pipeline is a separable project.
- **Multi-step wizard.** Discord's multi-step flow exists because of platform component limits we don't have on the web. The web form is one cohesive modal with conditional sections; no artificial step-throughs.
- **MMR auto-derivation from medal+star.** Selecting "Crusader 3" does not auto-fill numeric MMR. Admins continue to set the actual numeric MMR via `MmrApprovalModal` after signup.
- **Discord-side UX changes.** No new Discord buttons, modal layout changes, or embed-content changes. Only the internal Discord adapter changes — the user-visible Discord flow is unchanged.

## Constraints

- Backend: Django + DRF + Pydantic schemas; cacheops invalidation discipline (model-level cache, see `backend/backend/settings.py` `CACHEOPS` block — verify model-cache membership there, not from a skill snippet).
- Frontend: React 19, react-router (SSR + client), TanStack Query, react-hook-form + zod, shadcn-derived `FormField` stack, brand button system from `frontend/app/components/ui/buttons/`.
- Testing: backend tests via `just test::run`, Playwright E2E via `just test::pw::*`, populate-helper system per `testing` skill (registered in `backend/tests/populate/__init__.py::POPULATE_FUNCTIONS`).
- Brand: `docs/THEMING-GUIDE.md` is canon. All UI must pass the `/brand` review (see `docs/theming-guide/ai/references/`).
- Existing rich Discord signup flow must continue to work without behavior changes after the shared-service extraction (commit `33bacad4` shipped just days ago — minimize regression risk).

## Architecture Overview

A web user clicks **Sign Up** or **Tentative** on `/events/<id>`. The frontend evaluates the user's existing `dota_profile` (already returned by the event SSR/loader payload) against the event's config flags. Two paths:

- **Nothing missing** → button click fires `POST /api/events/<id>/signup/` immediately with `{ intent }` and an empty profile patch. No modal, no extra render.
- **Something missing** → opens `EventSignupModal`, prefilled with whatever exists. User fills the gaps, submits the same endpoint with the patched profile fields.

The new endpoint lives on `EventViewSet` as a DRF action. Its body is a thin orchestration: validate input → resolve `OrgUser` → call shared service inside `@transaction.atomic` → fire `notify_signup_changed` → return `EventSignupSerializer`.

The shared service module is the contract between Discord and web. The current Discord-only helpers in `events/discord/handlers.py` (`_save_dota_profile`, the position writes inside `PositionConfirmButton.callback`, the screenshot URL writes inside `handle_screenshot_upload`) are extracted into `events/services.py` as plain functions taking an `OrgUser` (because the `PlayerDotaProfile` hangs off `OrgUser`, not `CustomUser`) and a profile patch dict. Discord handlers become call-sites that build the same dict from interaction values and forward it. Web endpoint builds the same dict from the validated request body. Single canonical write path.

```
                       ┌──────────────────────────┐
   Discord interaction │  events/discord/handlers │
   (button → modal →   │  - _get_org_user()       │  (multiple calls per signup,
    select → submit;   │  - build patch dict      │   each its own transaction;
    spans up to        │  - call shared service   │   tokens are 15 min so no
    15-min token TTL)  └─────────┬────────────────┘   single tx covers all turns)
                                 │
                                 ▼
                       ┌──────────────────────────┐
                       │  events/services.py      │
                       │  - apply_signup_input()  │  (one call = one tx; idempotent
                       │  - process_rsvp()        │   on re-application of same
                       │  - create_tentative_…()  │   patch; tolerates partial
                       └─────────▲────────────────┘   prior state)
                                 │
                       ┌─────────┴────────────────┐
   POST /api/events/   │  EventViewSet.signup     │  (single call per web signup,
   <id>/signup/        │  - resolve OrgUser       │   wrapped in @transaction.atomic
                       │  - apply_signup_input    │   spanning profile + signup writes)
                       │  - process_rsvp / tent.  │
                       │  - notify_signup_changed │
                       └──────────────────────────┘
```

## Backend

### Shared service: `apply_signup_input`

New function in `events/services.py`:

```python
def apply_signup_input(*, org_user: OrgUser, event: Event, patch: SignupInputPatch) -> PlayerDotaProfile:
    """Idempotently write any provided fields onto the OrgUser's PlayerDotaProfile.

    Fields not in `patch` are not touched. Validates against `event` config flags
    (rank_status allowed, position range, screenshot URL shape) and raises
    DjangoValidationError on policy violations. Cacheops invalidation is registered
    via invalidate_after_commit so it is safe to call inside or outside an enclosing
    transaction.
    """
```

**Contract details that callers depend on:**

- Takes `OrgUser`, not `CustomUser`. The Discord adapters already resolve `OrgUser` via `_get_org_user(event, discord_user_id)` (which returns `(org_user, user)` and auto-creates both rows on first interaction). The web endpoint resolves it explicitly (see "Resolving OrgUser" below).
- **Multi-call semantics.** Discord writes the profile across 4–5 separate gateway turns (modal submit → position confirm → medal/star → screenshot upload). Each turn is its own transaction; Discord interaction tokens have a 15-minute TTL so no single transaction can span all turns. `apply_signup_input` therefore commits independently on each call. The web endpoint by contrast calls it once per signup, inside the request's `@transaction.atomic`. The function must work the same way in both contexts — it only invalidates *after commit* via `invalidate_after_commit`.
- **Partial state tolerance.** Policy validation must accept patches where some fields are absent (e.g., a `rank_medal: "Crusader 3"` arrives when `rank_status` is already saved on the profile from a prior turn). Validation runs against `merge(profile, patch)`, not against `patch` alone.
- **No completeness gating.** "Did the user provide every field the event requires?" is enforced *only* by `process_rsvp` (screenshot-required, `min_mmr` floor) and by client-side zod (Friend ID present, positions set, medal chosen). The shared service writes whatever it's given.

`SignupInputPatch` is a typed structure (Pydantic model in `events/schemas.py`) with all-optional fields:

| Field                    | Type                                       | Notes                                            |
| ------------------------ | ------------------------------------------ | ------------------------------------------------ |
| `unverified_friend_id`   | `str` (max 20)                             | Numeric not enforced; matches Discord laxity.    |
| `positions`              | `list[int]` ⊆ `{1,2,3,4,5}`                | Stored as five booleans on `PlayerDotaProfile`.  |
| `rank_status`            | `Literal["active", "previous", "never"]`   | Must be allowed by event config.                 |
| `rank_medal`             | `str` (e.g., `"Crusader 3"`, `"Immortal"`) | No length validation beyond Django field limit.  |
| `battle_cup_tier`        | `int` ∈ `{1..8}`                           |                                                  |
| `rank_screenshot`        | `str` (URL, max URLField length)           | `https?://…` shape check; `.png/.jpg/.jpeg/.webp` extension allowlist (matches Discord's existing rule). |
| `battlecup_screenshot`   | `str` (URL)                                | Same shape + extension rule.                     |

Validation rules embedded in this function (same rules Discord enforces today, surfaced once):

- `rank_status` must satisfy `event.allow_active_mmr` / `allow_previous_rank` / `allow_battlecup_rating` (no `discord_` prefix on these).
- Positions deduped, all in `{1..5}`; out of range → raise.
- Screenshot URL: `https?://…` shape + image extension allowlist.
- **Duplicate Friend ID check** (currently performed inside `handle_signup_modal_submit` at `events/discord/handlers.py:233-249`) moves *into* `apply_signup_input` so both surfaces share it. If `patch.unverified_friend_id` is set and another `OrgUser` in the same organization already owns that Friend ID, raise.

### Resolving `OrgUser` in the web endpoint

The web endpoint must produce an `OrgUser` for `request.user` in `event.organization` before calling `apply_signup_input`. Two cases:

- `OrgUser` already exists → use it.
- `OrgUser` doesn't exist → create one (this is what Discord does too, via `_get_org_user`). The user joining their first event becomes a member of the org.

We extract this resolution into a service helper `resolve_or_create_org_user(user, organization) -> OrgUser` so both surfaces use the same code. The Discord helper `_get_org_user` keeps its existing public shape (still returns `(org_user, user)`) but internally calls `resolve_or_create_org_user`.

### Cacheops invalidation rules

Cached models (per `backend/backend/settings.py` `CACHEOPS`): `events.event`, `events.eventsignup`, `org.orguser`, `org.playerdotaprofile`, plus `app.customuser` and many others. All four touched by this flow are cached.

`apply_signup_input` calls `invalidate_after_commit(profile, org_user, event)`:

- `profile` because we wrote to it.
- `org_user` because `EventSignupSerializer.get_dota_profile` (lines 418-444 of `events/serializers.py`) joins through it, and the `cached_as(Event, EventSignup, …)` blocks at `events/views.py:344, 359` declare `Event, EventSignup` as deps but not `PlayerDotaProfile`. Adding `org_user` to the invalidation set means any `cached_as` keyed on `OrgUser` (`app/views_main.py` has 19 such decorators including one on `OrgUser, CustomUser` at line 1101) is busted on profile change.
- `event` because the cached event payload (`event_detail:{pk}` and the list views) include `dota_profile` per signup; without invalidating `event`, those payloads go stale until the next `EventSignup` write.

Why `invalidate_after_commit`, not `invalidate_obj`: the web endpoint runs under `@transaction.atomic`, and `invalidate_obj` inside a transaction races commit (which is exactly the bug `app/cache_utils.py::invalidate_after_commit` exists to prevent — see its docstring). The Discord adapters today call `invalidate_obj` *outside* a transaction so they don't hit the race; once they call `apply_signup_input` instead, the safer helper is correct in both contexts.

`create_tentative_signup` calls `invalidate_after_commit(signup, signup.event)` — matching the original tentative branch in `views.py:522`. Note that the existing `_create_signup` (called by `process_rsvp`) at `events/services.py:145, 169` only invalidates `event`, not `signup` — that's a pre-existing pattern this spec does **not** change.

### New endpoint: `POST /api/events/<id>/signup/`

`@action(detail=True, methods=["post"])` on `EventViewSet`. Request body:

```json
{
  "intent": "rsvp" | "tentative",
  "profile": { /* SignupInputPatch fields, all optional */ }
}
```

Response: `EventSignupSerializer` payload (201 on creation), same shape `rsvp` and `tentative` returned previously.

Body flow:

1. `IsAuthenticated` permission.
2. Event state check: `event.state == SIGNUPS_OPEN`. Wrong state → 400 `{"error": "Event is not accepting signups"}`.
3. Body validation via Pydantic: unknown fields rejected; `intent` required; `profile` defaults to `{}`.
4. Resolve `org_user = resolve_or_create_org_user(request.user, event.organization)`.
5. `@transaction.atomic`:
   - `apply_signup_input(org_user=org_user, event=event, patch=body.profile)`.
   - Branch on `intent`:
     - `"rsvp"` → `process_rsvp(event, request.user)` (existing function — runs screenshot / `min_mmr` / auto-approve / waitlist logic and creates the `EventSignup`).
     - `"tentative"` → `create_tentative_signup(event, request.user)` (new service, extracted from `views.py:496–524`).
6. After commit (via `transaction.on_commit`): `notify_signup_changed(event)` so the Discord embed refreshes for users watching there.
7. Return `EventSignupSerializer(signup).data` with 201.

Errors map to 400 with `{"error": "..."}` (matches the existing error shape elsewhere in the API).

### Discord refactor

Adapters in `events/discord/handlers.py` change as follows:

- `handle_signup_modal_submit` continues to call `_get_org_user`, but the field-write portion becomes `apply_signup_input(org_user=org_user, event=event, patch={...})`. The duplicate Friend ID check moves into the shared service.
- `PositionConfirmButton.callback` (in `discordbot/components.py`) builds `patch={"positions": [...]}` and calls `apply_signup_input` instead of writing the booleans inline.
- `handle_rank_medal_select` and `handle_battle_cup_submit` build `{"rank_medal": …}` / `{"battle_cup_tier": …}` patches and call the shared service. The encoded `custom_id` fallback (`rank_star:{event_id}:{medal}`) used by `StarSelect` is preserved unchanged — the adapter still reassembles `"{medal} {star}"` (or `"Immortal"`) before passing `rank_medal`.
- `handle_screenshot_upload` builds `{"rank_screenshot": url}` or `{"battlecup_screenshot": url}` and forwards.
- `_save_dota_profile` is deleted.

Each adapter wraps its `apply_signup_input` call in `try/except DjangoValidationError` and translates the exception to the existing `{"action": "error", "message": "..."}` dict shape so `components.py` continues to render `interaction.response.send_message(..., ephemeral=True)` — no exception bubbles to the discord.py gateway.

`DiscordEventLog` writes (`_log_signup`, `_log_interaction`) stay in the adapters; the shared service does not log Discord-specific events.

### Tentative as a service

Extract `tentative` view-level logic (`backend/events/views.py:486–525`) into `events/services.py::create_tentative_signup(event, user) -> EventSignup`. Same duplicate-signup checks, same cancelled-row cleanup, returns the new signup. Calls `invalidate_after_commit(signup, signup.event)`.

### Removed endpoints

`POST /api/events/<id>/rsvp/` and `POST /api/events/<id>/tentative/` are **deleted**. Discord uses the service-layer functions via Python imports, never these HTTP endpoints. Keeping them as shims after removing the only frontend callers would violate the codebase's no-dead-code policy.

**Migration list — every direct caller that must change:**

Backend test files referencing these endpoints (based on a grep that the implementer must reproduce):

- `backend/events/tests/test_api.py` — tests including `test_rsvp_for_event`, `test_rsvp_duplicate_rejected`, `test_public_rsvp_still_rejected_during_roll_call`. Migrate to call `/signup/` with `{intent: "rsvp"}`.

Frontend Playwright specs (under `frontend/tests/playwright/e2e/16-events/`):

- `01-smoke.spec.ts`, `03-roll-call.spec.ts`, `04-discord-integration.spec.ts` — each uses `postWithCsrf` against `/rsvp/` or `/tentative/`. Migrate to `/signup/` with the `intent` discriminator.

Frontend hooks: `useRsvpMutation`, `useTentativeMutation` in `frontend/app/hooks/useEvent.ts` are deleted. The `event-upgrade-rsvp-btn` button at `frontend/app/routes/event.tsx:434` (Tentative → Sign Up upgrade) currently calls `rsvpMutation.mutate()`; it must be re-routed to `useSignupMutation` with `intent: "rsvp"` and the same skip-the-form / show-modal evaluation as the primary Sign Up button.

OpenAPI / schema-drift: `backend/app/tests/test_schema_drift.py` snapshot must be regenerated as part of this PR to reflect the endpoint replacement.

### Migrations

None. The schema already supports everything; we're only changing *who* writes it.

## Frontend

### File layout

All new components live under `frontend/app/components/events/`, mirroring existing modals (`EditEventModal.tsx`, `CreateEventModal.tsx`, `MmrApprovalModal.tsx`):

- `EventSignupModal.tsx` (root component)
- `EventSignupModal/FriendIdField.tsx`
- `EventSignupModal/RankStatusRadioGroup.tsx`
- `EventSignupModal/PositionPickerGrid.tsx`
- `EventSignupModal/RankDetailFields.tsx`
- `EventSignupModal/ScreenshotUrlField.tsx`
- `EventSignupModal/schema.ts` (zod schema builder, exported `SignupInputPatch = z.infer<typeof signupPatchSchema>`)
- `EventSignupModal/evaluateSignupGap.ts` (pure helper)
- `EventSignupModal/toPatch.ts` (pure helper)

Each component file starts with `'use client'` (React Server Components are off-limits because of hooks, RHF, and event handlers).

### `EventSignupModal` component

**Mount strategy:** `event.tsx` renders `{open && <EventSignupModal …/>}` so RHF + zod resolver are not instantiated until the user opens it. RHF state lives inside the modal component, not lifted to the page — keystroke-level re-renders stay isolated.

**Props:**

```ts
type EventSignupModalProps = {
  event: EventType;                    // already loaded on the page
  intent: 'rsvp' | 'tentative';        // set by which button opened it
  profile: DotaProfileData | null;     // current user's existing dota_profile
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

The component must include `<DialogTitle>` (a11y; brand review treats missing title as block-severity) — the title text reflects intent: "Sign Up for {event.name}" or "Mark Tentative for {event.name}".

On `onOpenChange(false)`, the form calls RHF `reset()` so values don't persist across reopens.

**Conditional sections** (each its own subcomponent for unit-testability):

1. **Friend ID** (`FriendIdField`): visible iff `event.require_steam_id && !profile?.unverified_friend_id`. Single `FormField` + `<Input>`; `inputMode="numeric"` (Friend IDs are numbers; matches Discord placeholder copy). `data-testid="signup-friend-id"`. **Note:** This gate is universal across game types — see `evaluateSignupGap` below.
2. **Rank Status** (`RankStatusRadioGroup`): visible iff `!profile?.rank_status`. Three options (`active` / `previous` / `never`) filtered by `event.allow_active_mmr` / `allow_previous_rank` / `allow_battlecup_rating`. Implemented as shadcn `<RadioGroup>` with custom `RadioGroupItem` styled as cards (matching Discord's emoji + description vocabulary). **Disallowed options are filtered out** of the rendered set, not rendered-then-disabled (cleaner a11y). `data-testid="signup-rank-status"`.
3. **Positions** (`PositionPickerGrid`): visible iff Dota 2 game type AND `!hasAnyPosition(profile)`. Implemented as shadcn `<ToggleGroup type="multiple">` with `<ToggleGroupItem>` for each of the five positions, using Discord's emoji + label vocabulary. Five booleans on `PlayerDotaProfile`. `data-testid="signup-positions"`.
4. **Rank Detail** (`RankDetailFields`):
   - When chosen status is `active` or `previous` → Medal `<Select>` (Herald → Immortal) + Star `<Select>` (1–5, hidden when medal is `Immortal`).
   - When `never` → Battle Cup Tier `<Select>` (1–8).
   `data-testid="signup-rank-medal"`, `signup-rank-star`, `signup-battlecup-tier`.
5. **Screenshot URL** (`ScreenshotUrlField`): visible iff event requires it for the chosen rank-status branch AND no existing URL on profile. `<Input type="url">` + `<FormDescription>` carrying the helper copy ("Upload your screenshot to imgur.com and paste the link here"). Validated as `https?://…` with `.png/.jpg/.jpeg/.webp` extension. `data-testid="signup-screenshot-url"`.
6. **Submit row**: brand `<SubmitButton loading={mutation.isPending}>` (label = "Sign Up" or "Mark Tentative" based on intent) + brand `<CancelButton>`. The `<SubmitButton>` wrapper wires `type="submit"` and the loading spinner; the `<CancelButton>` matches existing form-modal patterns (`MmrApprovalModal.tsx` is the reference). Submit disabled until zod schema is valid for the visible fields.

All `<RadioGroup>`, `<ToggleGroup>`, `<Select>` instances are wrapped via RHF `<Controller>` (uncontrolled won't bind cleanly to compound shadcn primitives).

### Form stack

Per the `zod-form-validation` skill: `react-hook-form` + `zodResolver`. The schema is built dynamically from `event` config + the user's `profile` so only fields that need filling are validated.

- `mode: 'onChange'` so the submit button can disable until the visible fields are valid.
- `shouldUnregister: true` so a field that becomes hidden (e.g., switching `rank_status` from `active` to `never` removes Medal/Star) doesn't carry stale values into the patch.
- The schema is memoized with `useMemo` keyed on `(event.id, event.require_steam_id, event.allow_active_mmr, event.allow_previous_rank, event.allow_battlecup_rating, event.discord_require_rank_screenshot, event.discord_require_battlecup_screenshot, profile-completeness flags)`. Without memoization the `zodResolver` identity changes per render and RHF re-validates from scratch every keystroke.
- `SignupInputPatch` type: `type SignupInputPatch = z.infer<typeof signupPatchSchema>`. This same type is used for form values, the `toPatch()` return value, and the Axios request body — single source of truth.

### Skip-the-form fast path

Implemented in `event.tsx`. Pure helper `evaluateSignupGap(event, profile)` returns either `'complete'` or a list of missing-section keys. Exported from a `helpers` file (`EventSignupModal/evaluateSignupGap.ts`) so it stays out of any client/server boundary worries.

```ts
function evaluateSignupGap(event: EventType, profile: DotaProfileData | null): 'complete' | string[] {
  const missing: string[] = [];

  // Friend ID gate is universal — applies to all game types.
  if (event.require_steam_id && !profile?.unverified_friend_id) missing.push('friend_id');

  // The rich profile gates apply only to Dota 2.
  if (event.game_type === GameType.DOTA2) {
    if (!profile?.rank_status) missing.push('rank_status');
    if (!hasAnyPosition(profile)) missing.push('positions');
    if (profile?.rank_status === 'active' || profile?.rank_status === 'previous') {
      if (!profile.rank_medal) missing.push('rank_medal');
    }
    if (profile?.rank_status === 'never' && profile.battle_cup_tier == null) missing.push('battle_cup_tier');
    if (event.discord_require_rank_screenshot &&
        (profile?.rank_status === 'active' || profile?.rank_status === 'previous') &&
        !profile.rank_screenshot) missing.push('rank_screenshot');
    if (event.discord_require_battlecup_screenshot &&
        profile?.rank_status === 'never' &&
        !profile.battlecup_screenshot) missing.push('battlecup_screenshot');
  }

  return missing.length === 0 ? 'complete' : missing;
}
```

`'complete'` → call the new endpoint immediately (no modal mount).
Non-empty list → set state to open the modal.

**Stale-profile defense.** The fast-path uses the `dota_profile` snapshot from the event SSR/loader payload. If the user updated their profile in another tab, that snapshot can be wrong. Mitigation:

- `useUserDotaProfile()` query in `frontend/app/hooks/useUserProfile.ts`, keyed on the current user's pk, that returns the freshest profile. The fast path reads from this query rather than from `event.user_data.dota_profile` so a stale event payload doesn't fool the gap evaluator.
- Any mutation that writes `PlayerDotaProfile` (this signup endpoint, future profile editor) invalidates `['user-dota-profile', userPk]`.

If the immediate fast-path call still returns 400 (defense in depth), the page re-fetches both queries and either opens the modal with the missing field highlighted or shows a toast.

### Mutation wiring

New `useSignupMutation(eventId)` in `frontend/app/hooks/useEvent.ts`. Posts to the new endpoint. On success, invalidates the same set of queries the existing `useRsvpMutation` invalidates plus the org-users cache:

```ts
queryClient.invalidateQueries({ queryKey: ['event', eventId] });
queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
queryClient.invalidateQueries({ queryKey: ['user-dota-profile', currentUserPk] });
useOrgStore.getState().clearOrgUsers();
```

The org-users clear matches `adminAddSignup` (which already does this because the backend may create an `OrgUser` row at signup time — same is true for the new endpoint, since first-time signers in an org get an `OrgUser` created by `resolve_or_create_org_user`).

`useRsvpMutation` and `useTentativeMutation` are deleted along with the `ConfirmDialog` "RSVP for Event" code path. The `event-upgrade-rsvp-btn` button's handler is rewired to `useSignupMutation` with `intent: "rsvp"` and the same `evaluateSignupGap` branch.

`useTransition` wraps the immediate fast-path call so the UI stays responsive during the round-trip; this is a polish detail, not a correctness requirement.

### Brand compliance

This is a `/brand` review surface. Specific requirements derived from `docs/THEMING-GUIDE.md` and its references:

- **Buttons inside the form modal:** `<SubmitButton loading={...}>` for submit, `<CancelButton>` for dismiss (per `component-substitutions.md`). `<PrimaryButton>` / `<SecondaryButton>` are *not* the right wrappers inside a `<form>` — they don't wire `type="submit"` or the loading spinner.
- **Page-level buttons** (Sign Up, Tentative on the event page header): brand `<PrimaryButton>` / `<SecondaryButton>` as today.
- **No raw `<button>`** anywhere; brand wrappers only.
- **`<DialogTitle>`** required (a11y, block-severity if missing).
- **Surfaces:** `bg-base-*` scale and tokens from `frontend/app/app.css`. No `bg-slate-*`, no inline violet/indigo hex, no `style={{}}`, no `bg-gradient-*` on `DialogContent`.
- **Class composition:** `cn()` only; no template-string concatenation.
- **Spacing:** `flex gap-*`, not `space-x-*` / `space-y-*`.
- **Sizing:** `size-*` for square boxes, not `w-N h-N`.
- **Touch targets:** `min-h-11` on radio cards, toggle pills, and select triggers (the most likely violators).
- **Form description text** ("Upload your screenshot to imgur.com…") uses `<FormDescription>`, never a styled `<p>`.
- **Error surface:** validation/server errors use `brandErrorBg` / `brandErrorCard` styles, never raw red.
- **Keyboard:** Enter submits when valid; Esc closes (shadcn `<Dialog>` defaults are sufficient — verify in implementation).

### Layout and responsive behavior

- **Desktop / tablet (≥ md):** `<Dialog>` with `<DialogContent className="max-h-[90vh] overflow-y-auto">`. Two-column layout for the position grid and medal+star pair.
- **Mobile (< md):** `<Drawer>` (bottom-sheet) variant, sticky submit row at the bottom so it stays reachable above the keyboard. Stacked layout throughout.
- **Hydration race:** if the user clicks Sign Up before `useEvent` / `useEventSignups` / `useUserDotaProfile` have all settled, the trigger button shows a spinner and is disabled. The buttons are gated on `event && signups && profile !== undefined`.

### Design craft

The form has up to 5 conditional sections; without visual rhythm a fresh user sees a wall. Required design moves:

- **Numbered section headings** ("1. Friend ID", "2. Positions", …) with section dividers (the brand's neon hairline style).
- **Prefilled-section collapse:** sections whose data is already on the user's profile render as a collapsed summary chip (e.g., "⚔️ Carry · Mid · Offlane — from your profile · Edit"). Click to expand and edit. This makes prefilled fields visually distinct from blanks and prevents re-asking.
- **Tentative differentiation:** modal title, header accent color, and submit button color differ between intents. Sign Up uses the brand emerald for the submit; Tentative uses amber. The header copy makes intent obvious ("You're marking yourself **tentative** — we count you as interested but not committed.").
- **Skip-the-form moment:** when the fast path fires, the page shows an inline confirmation chip in the header ("✅ Signed up — #4 in queue"), animated in with a 1.2s pulse, in addition to the toast. The toast alone leaves the moment flat.
- **Distinctive visual touches** consistent with "Neon Cyber Esports":
  - Position toggle pills color-coded to role (carry red, mid yellow, off teal, soft green, hard yellow — the same vocabulary Discord uses).
  - Medal pills color-tokened (Herald grey → Immortal red gradient).
  - Star-row reveal animates under the chosen medal; collapses for Immortal.
  - Submit button uses the brand violet→cyan gradient on hover.

These are spec requirements, not implementation suggestions. The brand review pass enforces them.

### Accessibility

- `<DialogTitle>` present (or `sr-only` if visually hidden — visible is preferred here).
- `aria-invalid` on fields with active validation errors; styled via `data-invalid` for the error state.
- `<Input type="url" inputMode="url">` for the screenshot URL field; `inputMode="numeric"` for the Friend ID field.
- Focus moves to the first focusable element on open (shadcn `<Dialog>` default); on close, focus returns to the button that opened it.
- Disallowed rank-status options are filtered out of the rendered set, not rendered-then-disabled.
- Keyboard nav: Tab cycles through visible fields and the submit/cancel pair; Enter submits; Esc closes.

### Dependencies

The shadcn `<RadioGroup>` primitive is **not currently installed** in this repo (`frontend/app/components/ui/` has no `radio-group.tsx`). The PR adds it via `npx shadcn@latest add radio-group`. `<ToggleGroup>` is already installed (`toggle-group.tsx`). No other new shadcn components are needed.

## Data Flow & Validation

### SSR / loader path

The event SSR loader (`/events/<id>/ssr/`) already returns `dota_profile` for the current user inside `EventSignupSerializer.user_data`. The event detail also exposes `require_steam_id`, `allow_active_mmr`, `allow_previous_rank`, `allow_battlecup_rating`, `discord_require_rank_screenshot`, `discord_require_battlecup_screenshot`, and `min_mmr`. New: `useUserDotaProfile()` query for the freshest profile (see "Stale-profile defense").

### Submit payload

```json
POST /api/events/123/signup/
{
  "intent": "rsvp",
  "profile": {
    "unverified_friend_id": "12345678",
    "positions": [1, 2, 3],
    "rank_status": "active",
    "rank_medal": "Crusader 3",
    "rank_screenshot": "https://i.imgur.com/abc123.png"
  }
}
```

Any field the user didn't change is omitted (the `toPatch(values, profile)` mapper diffs against the prefill). Empty `profile: {}` is the fast-path call.

### Server-side validation order

1. **Auth gate** — `IsAuthenticated`.
2. **Event state** — `event.state == SIGNUPS_OPEN`. Wrong state → 400.
3. **Body shape** — Pydantic validates the patch dict. Unknown fields rejected.
4. **Resolve `org_user`** via `resolve_or_create_org_user`.
5. **Policy validation in `apply_signup_input`** — rank-status allowed, position range, screenshot URL shape + extension, duplicate Friend ID check.
6. **Profile write** — runs inside the request's `@transaction.atomic`; cacheops invalidation is registered via `invalidate_after_commit(profile, org_user, event)`.
7. **Intent branch** — `process_rsvp` (which itself enforces `min_mmr` and screenshot-required hard gates) or `create_tentative_signup`.
8. **`notify_signup_changed(event)`** registered via `transaction.on_commit` so Discord embeds refresh after the DB state is durable.
9. **Response** — `EventSignupSerializer(signup).data`, 201 on creation.

### Idempotency

Re-submitting with `intent: 'rsvp'` while already actively signed up → 400 (matches existing behavior; `process_rsvp` enforces this). The frontend doesn't dedupe — the modal's submit button is disabled while the mutation is pending, and the page reads from the freshly invalidated query after success.

### Race with Discord

A user could click Sign Up on the website while their Discord modal is half-open. `process_rsvp` is already idempotent on "active signup exists" — the second submit (whichever side) returns the existing signup or a 400 "already signed up" error. The web mutation handles 400 by showing the server's error message via toast.

## Error Handling

### Server-side error shape

All failures return `400` with `{"error": "<human-readable message>"}`.

### Client-side display

- **Validation errors before submit** (zod): inline `<FormMessage>` under the offending field. Modal stays open; no toast.
- **Submit failure**: `toast.error(extractApiError(err))`; modal stays open; submit re-enables for retry.
- **Network failure**: same toast path.
- **Auth lapse**: 401 → existing axios interceptor handles re-auth.
- **Event state changed mid-fill**: 400 with the existing wording; toast; user closes the modal.

### Skip-the-form path errors

Same toast pipeline; no modal to leave open. A 400 on the fast path triggers a re-fetch of `useEvent` + `useUserDotaProfile`, then re-evaluates the gap. If the gap is now non-empty, the modal opens with the missing fields. Otherwise a toast surfaces the error and stops.

### Atomicity

`apply_signup_input` and the chosen signup-creation function run inside a single `@transaction.atomic` block on the action method. If the second step raises, the profile write rolls back and the registered `invalidate_after_commit` calls are *not* fired. The user sees one error and one consistent state.

### Logging

Match the existing `logger.info` / `logger.warning` calls on the prior `rsvp` action:

```
INFO  signup request: user=<pk>, event=<pk>, intent=rsvp, fields=[friend_id, positions, rank_status, rank_medal]
INFO  signup success: user=<pk>, event=<pk>, status=rsvp
WARN  signup rejected: user=<pk>, event=<pk>, reason="<error message>"
```

Logged via the `logging` skill conventions (`system=events`, `subsystem=signup`).

## Testing

### Backend unit tests

New file: `backend/events/tests/test_signup_input.py`.

- `apply_signup_input` writes each field correctly (parametrized: Friend ID, positions, rank-status branches, medal/star, battle cup tier, both screenshot URLs).
- Empty patch is a no-op.
- Disallowed `rank_status` raises `DjangoValidationError`.
- Positions outside `{1..5}` raise; deduped on save.
- Screenshot URL shape + extension allowlist.
- Duplicate Friend ID across `OrgUser`s in the same org raises.
- **Multi-call partial-patch contract** — call `apply_signup_input` 4 times in sequence with different patch slices (rank_status, then positions, then medal, then screenshot); final profile state matches all writes; each call is its own commit; no enclosing transaction. Mirrors how Discord exercises the function.
- **Cache invalidation** — spy on `invalidate_after_commit` (not `invalidate_obj`), assert it was called with `(profile, org_user, event)` after the transaction commits.
- **Rollback case** — wrap in `@transaction.atomic`, call `apply_signup_input`, then raise; assert `invalidate_after_commit` registrations are *not* fired (use `transaction.on_commit` introspection or a `TestCase` rather than `TransactionTestCase`).
- Idempotent on retry (apply same patch twice, no spurious DB writes).

### Backend API tests

New file: `backend/events/tests/test_signup_endpoint.py`.

- Unauthenticated → 401.
- Event not in `SIGNUPS_OPEN` → 400.
- Empty `profile` patch + complete profile → creates signup; status reflects auto-approve / pending-approval / waitlist correctly.
- Empty `profile` patch + incomplete profile → endpoint accepts the request and writes whatever is in the patch (i.e., nothing). Hard policy gates inside `process_rsvp` (screenshot required + missing, `min_mmr` floor) still surface as 400. Soft completeness gates (Friend ID present, positions set, medal chosen) are **not** server-enforced — they're enforced client-side via zod, matching Discord's `required=True` modal field semantics.
- `intent: 'tentative'` → creates tentative signup; duplicate tentative → 400.
- `intent: 'rsvp'` with full profile patch → profile fields persist AND signup is created (one transaction).
- Profile patch fails validation → no signup created (assert no `EventSignup` row).
- `process_rsvp` fails (e.g., `min_mmr` floor) → no profile write committed (transactional rollback test using `TransactionTestCase`).
- `OrgUser` is created on first signup for a user who isn't yet in the org.
- `notify_signup_changed` is called once after commit (spy on it; assert *after* the transaction has committed, not before).
- Discord-initiated signup followed by web-initiated signup → idempotent; second returns 400 "already signed up." Use `TransactionTestCase` so commits are visible across "actors."

### Backend Discord regression tests

The refactor touches multiple Discord adapter call sites. Existing test files cover them:

- `backend/discordbot/tests/test_components.py` — exercises `PositionConfirmButton`, `StarSelect`, `BattleCupTierSelect`, `ScreenshotUploadModal` callbacks directly. Add assertions that each callback now calls `apply_signup_input(...)` with the expected patch slice (spy).
- `backend/events/tests/test_signup_interactions.py` — assert `handle_signup_modal_submit` calls `apply_signup_input` with the full modal patch.
- `backend/events/tests/test_reaction_signup.py` — assert the reaction-driven signup path also routes through `apply_signup_input` (if it touches profile fields; otherwise add a smoke test that nothing regressed).
- `backend/events/tests/test_discord_integration.py` — end-to-end Discord flow continues to pass after the refactor; no functional change expected, but this test catches integration regressions.

The Discord-side `interaction.response.send_message(..., ephemeral=True)` UX path is preserved by the adapter-level `try/except DjangoValidationError`. Add a test that triggers a `ValidationError` from `apply_signup_input` (e.g., disallowed rank_status) and asserts the adapter sends an ephemeral error message rather than letting the exception propagate.

### Frontend unit tests (Vitest)

- `evaluateSignupGap(event, profile)` helper: parametrize over the full event-config × profile-completeness matrix, including the universal Friend-ID gate for non-Dota games.
- `toPatch(values, profile)` mapper: omits unchanged fields; includes only changed.
- `signupPatchSchema` builder: parametrized over event-config flags, asserts the right Zod fields are required vs optional.
- `EventSignupModal` component: render with various `event` + `profile` combinations, assert the right sections are visible/hidden and the right testids are present.

### Frontend E2E (Playwright)

New spec file: `frontend/tests/playwright/e2e/16-events/09-event-signup-form.spec.ts` (path conforms to the existing layout under `16-events/`; `08-` is the highest currently used prefix — verify and bump if a sibling specs has been added since).

Direct API calls in tests use `postWithCsrf` (DRF ViewSet pattern), pointing at the new `/signup/` endpoint.

Login fixtures: `loginEventPlayer` continues to be the baseline. A new fixture `loginEventPlayerCompleteProfile` provides a user whose `PlayerDotaProfile` is fully populated (Friend ID + positions + active rank with medal + screenshot). Either pin the `loginEventPlayer` profile shape in `tests/data/users.py` or add the dedicated fixture; spec leaves the choice to the implementer but mandates that the test writer not invent ad-hoc profile state per test.

Cases:

- **Happy path: complete profile.** Login as `loginEventPlayerCompleteProfile` → click Sign Up on an event with no screenshot requirement → assert no modal mounts → toast → user appears in Signups tab.
- **Happy path: incomplete profile, all sections.** Login as `loginEventPlayer` (empty profile) → click Sign Up → modal opens with Friend ID + Rank Status + Positions + Rank Detail visible → fill all fields → submit → modal closes, toast, user appears in Signups tab.
- **Conditional reveal.** Pick `rank_status="never"` → assert Battle Cup Tier select appears, Medal/Star do not.
- **Screenshot required.** Event with `discord_require_rank_screenshot=true` → modal includes screenshot URL input → bad URL shows inline error → good imgur URL submits.
- **Tentative path.** Click Tentative button → same modal with intent-differentiated header and submit label "Mark Tentative" → submit creates a tentative signup → user appears in Tentative tab.
- **Allow flags filter rank-status.** Event with `allow_active_mmr=false` → only "previous" and "never" radios render.
- **Friend ID universal-across-game-types.** Deadlock event with `require_steam_id=true` and a user whose profile has no Friend ID → clicking Sign Up opens the modal with only the Friend ID section visible (no positions/rank).
- **Upgrade tentative to RSVP.** Sign up as Tentative → click the Sign Up upgrade button → assert the same evaluation runs (modal opens for incomplete profile, fast-path fires for complete profile) → resulting status is `rsvp`-equivalent.
- **Mobile viewport.** Set `page.setViewportSize({ width: 375, height: 812 })` (matches commit `99217b1c` pattern) and use the `MobileNavDropdown` flow to navigate to the event. Open the form via the mobile-rendered Sign Up button. Assert the form is rendered as a `<Drawer>` (or full-bleed dialog), submit is sticky, fields stack, no horizontal scroll. Do **not** use Playwright's `devices['iPhone 14']`.

### `data-testid` inventory

The implementation must include all of:

- `event-signup-btn`, `event-tentative-btn` (existing; preserve).
- `event-signup-modal` (modal root).
- `event-signup-submit-btn`, `event-signup-cancel-btn`.
- `event-signup-error` (error surface inside the modal).
- `signup-friend-id`, `signup-rank-status`, `signup-positions`, `signup-rank-medal`, `signup-rank-star`, `signup-battlecup-tier`, `signup-screenshot-url`.
- `event-upgrade-rsvp-btn`, `event-cancel-rsvp-btn`, `event-cancel-tentative-btn`, `event-reinstate-btn` (existing; preserve).

### Schema-drift snapshot

`backend/app/tests/test_schema_drift.py` compares the live OpenAPI to a checked-in snapshot. The PR must regenerate the snapshot to reflect:

- Added: `POST /api/events/<id>/signup/`.
- Removed: `POST /api/events/<id>/rsvp/`, `POST /api/events/<id>/tentative/`.

### Test data — populate helper

New helper registered in `backend/tests/populate/__init__.py::POPULATE_FUNCTIONS` (and exported in `__all__`). The helper **reuses the existing org/league fixtures** — specifically `populate_events_data` (org 7 / league 7 / `event_player_1` per the `testing` skill's feature-isolation rule). It does not create a parallel org.

Responsibilities:

- Add one event with `discord_require_rank_screenshot=true` (re-uses org 7).
- Add one event without screenshot requirements.
- Ensure the `loginEventPlayer` user has an empty `PlayerDotaProfile` (or no profile at all).
- Ensure a `loginEventPlayerCompleteProfile` user has a fully populated `PlayerDotaProfile`.
- Idempotent on re-run (per testing skill rules).

## Rollout

- Single PR.
- Schema-drift snapshot regenerated in the same PR.
- Migration of existing `/rsvp/` and `/tentative/` test callers (backend `test_api.py`, Playwright `01-smoke.spec.ts`, `03-roll-call.spec.ts`, `04-discord-integration.spec.ts`) ships in the same PR — partial migration would leave CI red.
- No production data migrations; `cacheops` config is unchanged.
- Discord users see no change. Web users see the new modal/form.
- Rollback: revert the PR. Old endpoints come back along with the old hooks.

## Out-of-scope follow-ups

- **Deadlock signup form.** Mirror this design with the simpler Deadlock field set (Friend ID + free-text rank + last-played date).
- **Real file-upload pipeline.** Replace URL-paste with multipart upload to Cloudflare R2 (already used for static assets), serving presigned URLs for client-direct uploads. Migrate Discord's `URLField` to write R2 URLs too for consistency.
- **MMR auto-derivation.** Pre-fill `OrgUser.mmr` from medal+star using a published mapping table; admin retains override via `MmrApprovalModal`.
- **Profile editor.** A dedicated `/profile/dota` page so users can update positions / rank without going through an event signup. Builds on `useUserDotaProfile()` introduced here.
