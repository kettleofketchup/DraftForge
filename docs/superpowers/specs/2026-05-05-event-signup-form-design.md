# Event Signup Form — Design Spec

**Date:** 2026-05-05
**Status:** Draft v3 (pending implementation plan)
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
- A web-initiated signup ends up in the database **indistinguishable** from a Discord-initiated one — same `EventSignup`, same `PlayerDotaProfile` writes, same downstream admin flow, same `process_rsvp` business logic, same `notify_signup_changed` Discord-embed refresh (which `process_rsvp` already fires; see "Cacheops invalidation rules").
- Repeat web signups respect the user's prior profile data: nothing-missing-no-form fast path mirrors Discord's instant signup.
- Both **Sign Up** and **Tentative** buttons use the same form; only the resulting `EventSignup.status`, header copy, and submit-button label differ.
- A single canonical signup-input service is shared between Discord and web — no duplicated business logic.
- Brand-compliant per `docs/THEMING-GUIDE.md` (brand button system including `<SubmitButton>` / `<CancelButton>` for form modals; `bg-base-*`; no raw `<button>`).

## Non-goals

- **Deadlock rich form.** The Discord modal supports a Deadlock variant (free-text rank + last-played date). The Friend ID gate applies to all game types, but the rich Dota 2 form (positions, rank-status branch, medal/star/Battle Cup, screenshot) is **not** mirrored for Deadlock in this iteration. Deadlock signups continue through Discord, except for the universal Friend ID gate which the new web form does enforce.
- **File upload pipeline.** The codebase has no `MEDIA_ROOT`, `STORAGES`, or S3 client. Screenshots are URL-paste only (imgur or any `https?://…`), matching Discord's existing fallback. A real upload pipeline is a separable project.
- **Multi-step wizard.** Discord's multi-step flow exists because of platform component limits we don't have on the web. The web form is one cohesive modal with conditional sections; no artificial step-throughs.
- **MMR auto-derivation from medal+star.** Selecting "Crusader 3" does not auto-fill numeric MMR. Admins continue to set the actual numeric MMR via `MmrApprovalModal` after signup.
- **Discord-side UX changes.** No new Discord buttons, modal layout changes, or embed-content changes. Only the internal Discord adapter changes — the user-visible Discord flow is unchanged.
- **New brand tokens.** This spec does not introduce new color tokens (medal-per-medal palettes, position-role colors, neon-hairline divider, amber-tinted submit). The design-craft section identifies *opportunities* using only tokens that already exist in `frontend/app/app.css` and `frontend/app/components/ui/buttons/styles.ts`. Anywhere a desired token is missing, the implementation falls back to a brand-compliant alternative documented inline.

## Constraints

- Backend: Django + DRF + Pydantic schemas; cacheops invalidation discipline (model-level cache, see `backend/backend/settings.py` `CACHEOPS` block — verify model-cache membership there, not from a skill snippet).
- Frontend: React 19 patterns running under Vite + react-router SSR (this is **not** RSC; `'use client'` directives are decorative — included for forward compatibility but have no runtime effect today).
- Testing: backend tests via `just test::run`, Playwright E2E via `just test::pw::*`, populate-helper system per `testing` skill (registered in `backend/tests/populate/__init__.py::POPULATE_FUNCTIONS`).
- Brand: `docs/THEMING-GUIDE.md` is canon. All UI must pass the `/brand` review (see `docs/theming-guide/ai/references/`).
- Existing rich Discord signup flow must continue to work without behavior changes after the shared-service extraction (commit `33bacad4` shipped just days ago — minimize regression risk).

## Architecture Overview

A web user clicks **Sign Up** or **Tentative** on `/events/<id>`. The frontend evaluates the user's existing `dota_profile` against the event's config flags. Two paths:

- **Nothing missing** → button click fires `POST /api/events/<id>/signup/` immediately with `{ intent }` and an empty profile patch. No modal mounts.
- **Something missing** → opens `EventSignupModal`, prefilled with what exists. User fills the gaps, submits the same endpoint with the patched profile fields.

The new endpoint lives on `EventViewSet` as a DRF action. Its body is a thin orchestration: validate input → resolve `OrgUser` → call shared service inside `@transaction.atomic` → return `EventSignupSerializer`. The Discord-embed refresh (`notify_signup_changed`) is **not** called from the endpoint — `process_rsvp` and `create_tentative_signup` already register it via `transaction.on_commit` (see `services.py:146,170,235,…`). Calling it again from the endpoint would double-fire.

The shared service module is the contract between Discord and web. The current Discord-only helpers in `events/discord/handlers.py` (`_save_dota_profile`, the position writes inside `PositionConfirmButton.callback`, the screenshot URL writes inside `handle_screenshot_upload`) are extracted into `events/services.py` as plain functions taking an `OrgUser` (because the `PlayerDotaProfile` hangs off `OrgUser`, not `CustomUser`) and a profile patch dict. Discord handlers become call-sites that build the same dict from interaction values and forward it. Web endpoint builds the same dict from the validated request body. Single canonical write path.

```
                       ┌──────────────────────────┐
   Discord interaction │  events/discord/handlers │
   (button → modal →   │  - _get_org_user()       │  (multiple calls per signup,
    select → submit;   │  - build patch dict      │   each its own commit; tokens
    spans up to        │  - call shared service   │   are 15 min so no enclosing
    15-min token TTL)  └─────────┬────────────────┘   tx spans all turns)
                                 │
                                 ▼
                       ┌──────────────────────────┐
                       │  events/services.py      │
                       │  - apply_signup_input()  │  (one call = one commit unit;
                       │  - process_rsvp()        │   tolerates partial prior state;
                       │  - create_tentative_…()  │   notify_signup_changed fires
                       └─────────▲────────────────┘   from process_rsvp/tentative
                                 │                    via on_commit, not from caller)
                       ┌─────────┴────────────────┐
   POST /api/events/   │  EventViewSet.signup     │  (single call per web signup,
   <id>/signup/        │  - resolve OrgUser       │   wrapped in @transaction.atomic
                       │  - apply_signup_input    │   spanning profile + signup writes)
                       │  - process_rsvp / tent.  │
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
    DjangoValidationError(message=..., code=...) on policy violations. Cacheops
    invalidation is registered via invalidate_after_commit so it is safe to call
    inside or outside an enclosing transaction.
    """
```

**Contract details that callers depend on:**

- Takes `OrgUser`, not `CustomUser`. The Discord adapters resolve `OrgUser` via `_get_org_user(event, discord_user_id)` (which returns `(org_user, user)` and auto-creates both rows on first interaction). The web endpoint resolves it via the new `resolve_or_create_org_user` helper (see below). `_get_org_user` does **not** perform `discord_username` housekeeping on existing rows; it only sets `nickname` on first-time `CustomUser` creation.
- **Multi-call semantics.** Discord writes the profile across 4–5 separate gateway turns (modal submit → position confirm → medal/star → screenshot upload). Each turn is its own commit unit; Discord interaction tokens have a 15-minute TTL so no single transaction can span all turns. The function commits independently on each call. The web endpoint by contrast calls it once per signup, inside the request's `@transaction.atomic`. The function works the same way in both contexts because it only invalidates *after commit* via `invalidate_after_commit` — `cache_utils.py` registers via `transaction.on_commit`, which fires immediately when no transaction is active.
- **Partial state tolerance.** Policy validation runs against `merge(profile, patch)`, not against `patch` alone. Example: a `rank_medal: "Crusader 3"` patch arriving when `rank_status` is already saved on the profile from a prior turn is valid; only the merged state is checked.
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

Validation rules embedded in this function:

- `rank_status` must satisfy `event.allow_active_mmr` / `allow_previous_rank` / `allow_battlecup_rating`.
- Positions deduped, all in `{1..5}`.
- Screenshot URL: `https?://…` shape + image extension allowlist.
- **Duplicate Friend ID check**: if `patch.unverified_friend_id` is set and another `OrgUser` in `event.organization` already owns that Friend ID, raise.

**Error message vocabulary** (preserved verbatim from existing Discord adapters so the user-facing copy doesn't regress when the check moves into the service). The service raises with these strings; adapters render them via `interaction.response.send_message(..., ephemeral=True)`:

| Validation failure                        | Message                                                                                                                                                  |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rank_status="active"`, not allowed       | `"This event does not accept active MMR signups."`                                                                                                       |
| `rank_status="previous"`, not allowed     | `"This event does not accept previous-rank signups."`                                                                                                    |
| `rank_status="never"`, not allowed        | `"This event does not accept Battle Cup–only signups."`                                                                                                  |
| Position out of range                     | `"Invalid position. Must be 1–5."`                                                                                                                        |
| Battle Cup tier out of range              | `"Invalid tier. Must be a number from 1 to 8."`                                                                                                           |
| Screenshot URL bad shape / extension      | `"Screenshot must be a direct .png/.jpg/.jpeg/.webp URL."`                                                                                               |
| Duplicate Friend ID                       | `"Friend ID {fid} is already registered to another player. Contact an admin or login to https://dota.kettle.sh to claim it."` (preserved from `handlers.py:241`) |

Each `DjangoValidationError` carries a stable `code` string (e.g., `code="rank_status_disallowed"`, `code="duplicate_friend_id"`) so adapters can branch on machine-readable identifiers and tests can assert on codes rather than fragile prose.

### Resolving `OrgUser` in the web endpoint

The web endpoint produces an `OrgUser` for `request.user` in `event.organization` before calling `apply_signup_input`. Two cases:

- `OrgUser` already exists → use it.
- `OrgUser` doesn't exist → create one (matching what Discord does via `_get_org_user`, and what `staff_add_signup` and `approve_signup` already do at `services.py:191-192,217`).

We extract this resolution into a service helper `resolve_or_create_org_user(user, organization) -> OrgUser`. The Discord helper `_get_org_user` keeps its existing public shape (still returns `(org_user, user)` and auto-creates `CustomUser` from `discord_user_id` when needed) but its `OrgUser`-creation half delegates to `resolve_or_create_org_user`. `staff_add_signup` and `approve_signup` are migrated to call `resolve_or_create_org_user` too — single source of truth for "user joins org by signing up."

### Cacheops invalidation rules

Cached models verified against `backend/backend/settings.py` `CACHEOPS` block: `events.event`, `events.eventsignup`, `org.orguser`, `org.playerdotaprofile`, plus many others. All four touched by this flow are cached.

**`apply_signup_input` calls `invalidate_after_commit(profile, org_user, event)`** with this rationale:

- `profile` because we wrote to it.
- `org_user` because the cached payloads at `app/views_main.py:1101` (`cached_as(OrgUser, CustomUser, …)`) are model-level deps — cacheops registers a conjunction matching *any* `OrgUser` save, so `invalidate_after_commit(org_user)` busts every cache keyed on OrgUser writes for that org. (This is correct semantics for what we need: a profile change should bust the org-user-keyed payloads that include dota fields.)
- `event` because the cached event payload (`event_detail:{pk}` and the list views via `cached_as(Event, EventSignup, …)` at `events/views.py:344, 359`) embeds `dota_profile` per signup; without invalidating `event`, those payloads go stale until the next `EventSignup` write.

**Why `invalidate_after_commit`, not `invalidate_obj`:** the web endpoint runs under `@transaction.atomic`, and `invalidate_obj` inside a transaction races commit (the bug `cache_utils.py::invalidate_after_commit` exists to prevent — see its docstring). The Discord adapters today call `invalidate_obj` *outside* a transaction so they don't hit the race; once they call `apply_signup_input` instead, the safer helper is correct in both contexts. `cache_utils.py` registers via `transaction.on_commit`, which fires immediately when no transaction is active.

**`create_tentative_signup` calls `invalidate_after_commit(signup, signup.event)`** — matching the original tentative branch in `views.py:522`.

**Pre-existing patterns this spec does not change:**

- `_create_signup` (called by `process_rsvp`) at `services.py:145, 169` invalidates `event` only, not `signup`. This is harmless because cacheops auto-tracks the new `EventSignup` save via its write-side hooks, busting `cached_as(Event, EventSignup, …)` automatically.
- `notify_signup_changed` is registered via `transaction.on_commit` inside `_create_signup` and `create_tentative_signup` themselves. The web endpoint does not call it again.
- `CACHEOPS_DEGRADE_ON_FAILURE = True` (`settings.py:366`) means under Redis outage writes succeed but invalidations no-op. The new endpoint inherits this behavior; no special handling.

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
     - `"rsvp"` → `process_rsvp(event, request.user)` (existing function; itself fires `notify_signup_changed` via `on_commit`).
     - `"tentative"` → `create_tentative_signup(event, request.user)` (new service; also fires `notify_signup_changed` via `on_commit`).
6. Return `EventSignupSerializer(signup).data` with 201.

Errors map to 400 with `{"error": "..."}` carrying the message strings from the table above (or the prose from `process_rsvp` for hard-gate failures like `min_mmr`).

### Discord refactor

Adapters in `events/discord/handlers.py` and `discordbot/components.py` change as follows:

- `handle_signup_modal_submit` continues to call `_get_org_user`, but the field-write portion becomes `apply_signup_input(org_user=org_user, event=event, patch={...})`. The duplicate Friend ID check moves into the shared service.
- `PositionConfirmButton.callback` (in `discordbot/components.py`) builds `patch={"positions": [...]}` and calls `apply_signup_input` instead of writing the booleans inline.
- `handle_rank_medal_select` and `handle_battle_cup_submit` build `{"rank_medal": …}` / `{"battle_cup_tier": …}` patches. The encoded `custom_id` fallback (`rank_star:{event_id}:{medal}`) used by `StarSelect` is preserved unchanged — the adapter still reassembles `"{medal} {star}"` (or `"Immortal"`) before passing `rank_medal`.
- `handle_screenshot_upload` builds `{"rank_screenshot": url}` or `{"battlecup_screenshot": url}` and forwards.
- `_save_dota_profile` is deleted.

Each adapter wraps its `apply_signup_input` call in `try/except DjangoValidationError` and translates the exception to the existing `{"action": "error", "message": str(exc)}` dict shape so `components.py` continues to render `interaction.response.send_message(..., ephemeral=True)` with the exact message text from the vocabulary table — no exception bubbles to the discord.py gateway.

`DiscordEventLog` writes (`_log_signup`, `_log_interaction`) stay in the adapters; the shared service does not log Discord-specific events.

**Persistent-view registration (`EventSignupView`, `SignupButton`, `EventSignupModal` UI class, `PositionSelectView`, `RankStatusSelectView`, `RankDetailsView`) is unchanged.** All `custom_id` formats (`event_signup:{id}`, `rank_star:{event_id}:{medal}`, etc.) remain identical so existing button-message rows on Discord continue to dispatch to the refactored adapter callbacks after the bot restarts.

**`events/discord/reactions.py`** (reaction-driven signup path) does not write profile fields — it only creates `EventSignup` rows for users with already-complete profiles via `process_rsvp`. No refactor needed there. Spec adds a smoke test asserting it still works.

**Pre-existing redundancy (not introduced here, not fixed here):** `events/discord/handlers.py:177, 606, 651` directly call `notify_signup_changed(event)` after `process_rsvp` succeeds, even though `process_rsvp` itself already registers it via `on_commit`. The result is a double-fire from Discord-initiated signups — pre-existing behavior. This spec does not consolidate it; doing so risks regressing the embed-refresh timing in ways better debugged in a focused PR.

### Tentative as a service

Extract `tentative` view-level logic (`backend/events/views.py:486–525`) into `events/services.py::create_tentative_signup(event, user) -> EventSignup`. Same duplicate-signup checks, same cancelled-row cleanup, returns the new signup. Calls `invalidate_after_commit(signup, signup.event)` and registers `notify_signup_changed` via `on_commit`.

### Removed endpoints

`POST /api/events/<id>/rsvp/` and `POST /api/events/<id>/tentative/` are **deleted**. Discord uses the service-layer functions via Python imports, never these HTTP endpoints. Keeping them as shims after removing the only frontend callers would violate the codebase's no-dead-code policy.

**Migration list — every direct caller that must change:**

Backend test files referencing these endpoints:

- `backend/events/tests/test_api.py` — tests including `test_rsvp_for_event`, `test_rsvp_duplicate_rejected`, `test_public_rsvp_still_rejected_during_roll_call`. Migrate to call `/signup/` with `{intent: "rsvp"}`.

Frontend Playwright specs (under `frontend/tests/playwright/e2e/16-events/`):

- `01-smoke.spec.ts`, `03-roll-call.spec.ts`, `04-discord-integration.spec.ts` — each uses `postWithCsrf` against `/rsvp/` or `/tentative/`. Migrate to `/signup/` with the `intent` discriminator.

Frontend hooks: `useRsvpMutation`, `useTentativeMutation` in `frontend/app/hooks/useEvent.ts` are deleted. The `event-upgrade-rsvp-btn` button at `frontend/app/routes/event.tsx:434` (Tentative → Sign Up upgrade) currently calls `rsvpMutation.mutate()`; it is rewired to `useSignupMutation` with `intent: "rsvp"` and runs the same `evaluateSignupGap` evaluation as the primary Sign Up button.

OpenAPI / schema-drift: `backend/app/tests/test_schema_drift.py` snapshot must be regenerated. The PR also adds an explicit assertion that `/api/events/{id}/signup/` exists in the snapshot (catches accidental future removal).

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
- `EventSignupModal/PrefilledSummaryChip.tsx` (collapsed-section summary)
- `EventSignupModal/schema.ts` (zod schema builder, exports `SignupInputPatch = z.infer<typeof signupPatchSchema>`)
- `EventSignupModal/evaluateSignupGap.ts` (pure helper)
- `EventSignupModal/toPatch.ts` (pure helper)

Each component file starts with `'use client'`. (Vite + react-router does not use RSC today, so the directive is decorative; included for forward compatibility.)

### `EventSignupModal` component

**Mount strategy:** `event.tsx` renders `{open && <EventSignupModal …/>}` so RHF + zod resolver are not instantiated until the user opens it. The remount-on-open semantics mean RHF state resets naturally on close — no explicit `reset()` call is needed (and the spec's earlier `reset()` requirement is dropped to avoid implementer confusion).

**Props:**

```ts
type EventSignupModalProps = {
  event: EventType;                                    // already loaded on the page
  intent: 'rsvp' | 'tentative';                        // set by which button opened it
  profile: DotaProfileData | null | undefined;         // freshest profile (see ownership below)
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

**Profile ownership.** The `profile` prop is the result of `useUserDotaProfile()` (see "Stale-profile defense"), not the SSR snapshot from `event.user_data.dota_profile`. The parent (`event.tsx`) reads the query and passes its data through. This guarantees the modal sees the freshest source; the SSR snapshot only feeds `useUserDotaProfile()` as `initialData`.

The component must include `<DialogTitle>`. The title text reflects intent:

- Sign Up: `"Sign Up for {event.name}"`
- Tentative: `"Mark Tentative for {event.name}"`

Beneath the title, an intent banner row carries copy that makes the difference obvious:

- Sign Up: `"You're committing to play this event. We'll add you to the signup list."`
- Tentative: `"You're marking yourself tentative — we count you as interested but not committed."`

The banner uses the existing `<Badge>` component (`frontend/app/components/ui/badge.tsx`) with brand-existing token variants. It does **not** introduce a new color token; visual differentiation between intents comes from copy + an existing `Badge` variant (e.g., `variant="default"` for Sign Up, `variant="secondary"` for Tentative).

### Layout primitives

- **Dialog vs Sheet (responsive):** desktop (≥ md) uses `<Dialog>` with `<DialogContent className="max-h-[90vh] overflow-y-auto">`. Mobile (< md) uses **`<Sheet side="bottom">`** (already installed at `frontend/app/components/ui/sheet.tsx`). `<Drawer>` is *not* used because it isn't installed and adding `vaul` is out of scope. The sheet has a sticky submit row at the bottom so it stays reachable above the keyboard.
- **iOS Safari keyboard handling:** spec calls out the known issue where iOS Safari pushes bottom sheets under the on-screen keyboard. Mitigation: the `<Sheet>`'s scroll container uses `100dvh` (or `[height:100svh]`) and adds the `interactive-widget=resizes-content` viewport hint to the page metadata. The implementation must verify this on a real device.
- **Hydration race:** if the user clicks Sign Up before `useEvent` / `useEventSignups` / `useUserDotaProfile` have settled, the trigger button shows a spinner and is disabled. Trigger gating: `event && signups && profileQuery.status === 'success'`.

### Conditional sections

Each section is its own subcomponent for unit-testability. Sections whose data is already on the user's profile render as a collapsed **`<Collapsible>`** (`frontend/app/components/ui/collapsible.tsx`, already installed) with a summary chip — see "Design craft" below.

1. **Friend ID** (`FriendIdField`): visible iff `event.require_steam_id && !profile?.unverified_friend_id`. Single `FormField` + `<Input inputMode="numeric" pattern="[0-9]*">`. `data-testid="signup-friend-id"`. **Note:** This gate is universal across game types — see `evaluateSignupGap` below.
2. **Rank Status** (`RankStatusRadioGroup`): visible iff `!profile?.rank_status`. Three options (`active` / `previous` / `never`) filtered by `event.allow_active_mmr` / `allow_previous_rank` / `allow_battlecup_rating`. Implemented as shadcn `<RadioGroup>` with custom `<RadioGroupItem>` styled as label-wrapped clickable cards (matches Discord's emoji + description vocabulary). **Disallowed options are filtered out** of the rendered set, not rendered-then-disabled (cleaner a11y). `data-testid="signup-rank-status"`.
3. **Positions** (`PositionPickerGrid`): visible iff Dota 2 game type AND `!hasAnyPosition(profile)`. Implemented as shadcn `<ToggleGroup type="multiple">` with `<ToggleGroupItem>` per position. Discord's emoji set is preserved verbatim (1=⚔️, 2=🎯, 3=🛡️, 4=💚, 5=💛 — see `discordbot/components.py:57-62`). The group has `aria-label="Preferred positions"`. **Number↔string adapter:** since `<ToggleGroup type="multiple">` value is `string[]` but our form stores `number[]`, the `<Controller>` wraps the underlying ToggleGroup with `value={field.value.map(String)}` and `onValueChange={(values) => field.onChange(values.map(Number))}`. `data-testid="signup-positions"`.
4. **Rank Detail** (`RankDetailFields`):
   - When chosen status is `active` or `previous` → Medal `<Select>` (Herald → Immortal) + Star `<Select>` (1–5, hidden when medal is `Immortal`). Both `<Select>`s have `key={rankStatus}` so switching rank-status branches forces remount and clears Radix's internal `defaultValue` state.
   - When `never` → Battle Cup Tier `<Select>` (1–8) with the same `key={rankStatus}` pattern.
   `data-testid="signup-rank-medal"`, `signup-rank-star`, `signup-battlecup-tier`.
5. **Screenshot URL** (`ScreenshotUrlField`): visible iff event requires it for the chosen rank-status branch AND no existing URL on profile. `<Input type="url" inputMode="url">` + `<FormDescription>` carrying the helper copy ("Upload your screenshot to imgur.com and paste the link here"). Validated as `https?://…` with `.png/.jpg/.jpeg/.webp` extension. `data-testid="signup-screenshot-url"`.
6. **Submit row**: brand `<SubmitButton loading={mutation.isPending}>` + brand `<CancelButton>`. The `<SubmitButton>` wrapper hard-wires `type="submit"` and the success variant (which is the canonical brand violet→blue gradient via `brandGradient` in `styles.ts`); we do **not** recolor the submit per intent because that requires inventing a new wrapper variant. Intent differentiation lives in the title + banner (point 0 above), not in the submit-button color. `<CancelButton>` is disabled (not `loading`) while the mutation is pending. The submit button label reflects intent: "Sign Up" or "Mark Tentative". Submit disabled until zod schema is valid for the visible fields.

All `<RadioGroup>`, `<ToggleGroup>`, `<Select>` instances are wrapped via RHF `<Controller>`.

### Form stack

Per the `zod-form-validation` skill: `react-hook-form` + `zodResolver`. The schema is built dynamically from `event` config + the user's `profile`.

- `mode: 'onChange'` so the submit button can disable until visible fields are valid.
- `shouldUnregister: true` so a hidden field's stale value doesn't leak into the patch.
- The schema is memoized with `useMemo` keyed on the **specific values** that drive section visibility — listed explicitly so the dep array is correct: `[event.id, event.require_steam_id, event.allow_active_mmr, event.allow_previous_rank, event.allow_battlecup_rating, event.discord_require_rank_screenshot, event.discord_require_battlecup_screenshot, profile?.unverified_friend_id != null, profile?.rank_status, profile?.rank_medal != null, profile?.battle_cup_tier != null, hasAnyPosition(profile), profile?.rank_screenshot != null, profile?.battlecup_screenshot != null]`.
- **Default values** for newly-registered fields (when the user toggles `rank_status` and a different field branch shows) are set via the schema builder's `defaultValues` to avoid an "Invalid" flash. For `Battle Cup Tier`, default is `undefined` and the field uses `mode: 'onTouched'`-equivalent behavior (don't show the error until the user has interacted).
- `SignupInputPatch` type: `type SignupInputPatch = z.infer<typeof signupPatchSchema>`. This same type is used for form values, the `toPatch()` return, and the Axios request body — single source of truth.

### Skip-the-form fast path

Implemented in `event.tsx`. Pure helper `evaluateSignupGap(event, profile)` returns either `'complete'` or a list of missing-section keys. Exported from `EventSignupModal/evaluateSignupGap.ts` so it stays out of any client/server boundary worries.

```ts
function evaluateSignupGap(event: EventType, profile: DotaProfileData | null | undefined): 'complete' | string[] {
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

**Stale-profile defense.** New `useUserDotaProfile()` hook in `frontend/app/hooks/useUserProfile.ts` keyed on the current user's pk:

- `queryKey: ['user-dota-profile', userPk]`.
- `initialData` from `event.user_data.dota_profile` (if present in the SSR/loader payload).
- `staleTime: 30_000` (30s — fresh enough for a signup decision; cheap to refetch).
- `placeholderData: keepPreviousData` (no flicker on refetch).
- `refetchOnMount: 'always'` if the SSR snapshot is older than `staleTime`; otherwise relies on `initialData`.

Any mutation that writes `PlayerDotaProfile` (this signup endpoint, future profile editor) invalidates `['user-dota-profile', userPk]`. If the immediate fast-path call returns 400 (defense in depth), the page re-fetches both queries and either opens the modal with the missing fields or shows a toast.

**Pending state on the trigger buttons.** The Sign Up and Tentative buttons on the event page page are gated on `mutation.isPending` — disabled with a spinner during the round-trip. This avoids the "frozen button" feel a synchronous `mutate()` from a brand `<PrimaryButton>` produces. `useTransition` is **not** used here (TanStack mutations already manage their own pending state; wrapping in `startTransition` adds no benefit and can mask click feedback).

### Mutation wiring

New `useSignupMutation(eventId)` in `frontend/app/hooks/useEvent.ts`. Posts to the new endpoint. On success, invalidates the same set of queries the existing `useRsvpMutation` invalidates plus the org-users cache and the new profile query:

```ts
queryClient.invalidateQueries({ queryKey: ['event', eventId] });
queryClient.invalidateQueries({ queryKey: ['event-signups', eventId] });
queryClient.invalidateQueries({ queryKey: ['user-dota-profile', currentUserPk] });
useOrgStore.getState().clearOrgUsers();
```

The org-users clear matches `adminAddSignup` (which already does this because the backend may create an `OrgUser` row at signup time — same is true for the new endpoint, since first-time signers in an org get an `OrgUser` created by `resolve_or_create_org_user`).

`useRsvpMutation` and `useTentativeMutation` are deleted along with the `ConfirmDialog` "RSVP for Event" code path. The `event-upgrade-rsvp-btn` button is rewired to `useSignupMutation` with `intent: "rsvp"` and the same `evaluateSignupGap` branch (so upgrading from Tentative to Sign Up may open the modal if the user's profile is incomplete).

### Brand compliance

This is a `/brand` review surface. Specific requirements derived from `docs/THEMING-GUIDE.md` and its references, expressed against tokens that **already exist** in `frontend/app/app.css` and `frontend/app/components/ui/buttons/styles.ts`:

- **Buttons inside the form modal:** `<SubmitButton loading={...}>` for submit, `<CancelButton>` for dismiss. Page-level Sign Up / Tentative buttons stay as `<PrimaryButton>` / `<SecondaryButton>`. No raw `<button>`.
- **`<DialogTitle>`** required (a11y, block-severity if missing).
- **Surfaces:** `bg-base-*` scale and tokens from `app.css`. No `bg-slate-*`, no inline violet/indigo hex, no `style={{}}`, no `bg-gradient-*` on `DialogContent`.
- **Class composition:** `cn()` only.
- **Spacing:** `flex gap-*`, not `space-x-*` / `space-y-*`.
- **Sizing:** `size-*` for square boxes, not `w-N h-N`.
- **Touch targets:** `min-h-11` on radio cards, toggle pills, and select triggers.
- **Form description text** uses `<FormDescription>`; never a styled `<p>`.
- **Error surface:** validation/server errors use `brandErrorBg` / `brandErrorCard` styles, never raw red.
- **Focus ring:** `ring-ring` on radio cards and toggle pills.
- **Keyboard:** Enter submits when valid; Esc closes (shadcn `<Dialog>` and `<Sheet>` defaults are sufficient — verify in implementation that focus returns to the opener button on close).
- **Submit gradient:** the existing `brandGradient` (violet→**blue**, not violet→cyan) supplied automatically by `<SubmitButton>`. The spec must not invent a custom gradient.

### Design craft

The form has up to 5 conditional sections; without visual rhythm a fresh user sees a wall. Required design moves, all using existing primitives and tokens:

- **Numbered section headings** ("1. Friend ID", "2. Positions", …). Section dividers use the existing `border-t border-border` pattern from `EditEventModal.tsx` rather than a new "neon hairline" utility.
- **Prefilled-section collapse:** sections whose data is already on the user's profile render as a collapsed `<Collapsible>` with a `<Badge>` summary chip (e.g., "Carry · Mid · Offlane — from your profile"). The chip shows the values without emoji glyphs in the body copy (per the project's no-emoji-in-UI rule — emojis only in trigger buttons / Discord-vocabulary surfaces). Click anywhere on the chip or the trigger expands the section. An "Edit" icon-button affordance lives at the right edge of the chip. Esc inside expanded collapses; Enter on the chip expands. Reduced-motion fallback (`@media (prefers-reduced-motion)`) suppresses the height-auto transition.
- **Intent differentiation:**
  - Modal title carries intent ("Sign Up for X" / "Mark Tentative for X").
  - The intent banner row beneath the title carries the explanatory copy listed under "EventSignupModal component" above.
  - Page-level trigger buttons keep their existing visual treatment: Sign Up is `<PrimaryButton>` (which is the brand emerald-via-`brandGradient` look), Tentative is `<SecondaryButton>`. The spec does not introduce an amber variant.
  - Submit button color is **not** intent-differentiated — `<SubmitButton>` is hard-wired to the brand success variant. Differentiation comes from copy + Badge variant.
- **Skip-the-form moment:** when the fast path fires, the page shows a toast (existing pattern, primary feedback channel) and the existing button-set re-renders via the invalidated queries (Sign Up button → Cancel RSVP button, matching the current event-page behavior). The `<Badge>` summary chip in the page header that the design-craft v2 review mentioned is **dropped from this spec** — it duplicates the existing `EventStateBadge` and the button morph already provides positional confirmation. Toast remains, with `aria-live="polite"` (toast already does this via Sonner defaults).
- **Position pills:** styled as `<ToggleGroupItem>`s with the Discord emoji glyph + position number. Color treatment uses the existing `bg-base-*` selected/hover states from the toggle-group primitive, not invented role-color tokens. (The spec previously called for "carry red, mid yellow, off teal, soft green, hard yellow" — those are *Discord vocabulary* but no matching frontend tokens exist; introducing them would require a precursor brand-token PR. Out of scope here.)
- **Medal pills:** styled as `<Select>` items with the medal name. No per-medal color gradient (same reasoning: tokens don't exist). The Star `<Select>` reveals beneath the Medal `<Select>` after selection; reveal is a height-auto transition with a 60ms delay per star line for a subtle stagger; `prefers-reduced-motion` disables the stagger.
- **Loading skeleton:** if the user opens the modal while `useUserDotaProfile()` is still loading (rare given the `initialData` from SSR), the modal renders skeleton bars in section slots until the profile arrives — no spinner overlay.

### Accessibility

- `<DialogTitle>` present and visible.
- `aria-invalid` on fields with active validation errors; styled via `data-invalid`.
- `<Input type="url" inputMode="url">` for the screenshot URL field; `inputMode="numeric" pattern="[0-9]*"` for Friend ID.
- Focus moves to the first focusable element on open (shadcn `<Dialog>`/`<Sheet>` default); on close, focus returns to the opener button.
- Disallowed rank-status options are filtered out of the rendered set, not rendered-then-disabled.
- Keyboard nav: Tab cycles through visible fields and the submit/cancel pair; Enter submits; Esc closes.
- `<ToggleGroup>` carries `aria-label="Preferred positions"`; individual toggle items expose `aria-pressed`.
- `<Collapsible>` summary chips are keyboard-operable: Enter/Space expands, Esc collapses, focus moves into the expanded section.
- Animation respects `prefers-reduced-motion`.

### Dependencies

- `<RadioGroup>` is **not currently installed** (`frontend/app/components/ui/` has no `radio-group.tsx`). The PR adds it via `npx shadcn@latest add radio-group`.
- `<ToggleGroup>` is already installed (`toggle-group.tsx`).
- `<Sheet>` is already installed (`sheet.tsx`); used as the mobile responsive variant.
- `<Collapsible>` is already installed (`collapsible.tsx`).
- `<Badge>` is already installed (`badge.tsx`).
- No new top-level npm packages.

## Data Flow & Validation

### SSR / loader path

The event SSR loader (`/events/<id>/ssr/`) already returns `dota_profile` for the current user inside `EventSignupSerializer.user_data`. The event detail also exposes `require_steam_id`, `allow_active_mmr`, `allow_previous_rank`, `allow_battlecup_rating`, `discord_require_rank_screenshot`, `discord_require_battlecup_screenshot`, and `min_mmr`. New: `useUserDotaProfile()` query hydrated from the SSR snapshot via `initialData`.

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
5. **Policy validation in `apply_signup_input`** — rank-status allowed, position range, screenshot URL shape + extension, duplicate Friend ID check, with verbatim error messages from the vocabulary table.
6. **Profile write** — runs inside the request's `@transaction.atomic`; cacheops invalidation registered via `invalidate_after_commit(profile, org_user, event)`.
7. **Intent branch** — `process_rsvp` (which itself enforces `min_mmr` and screenshot-required hard gates and registers `notify_signup_changed` via `on_commit`) or `create_tentative_signup` (also registers `notify_signup_changed`).
8. **Response** — `EventSignupSerializer(signup).data`, 201 on creation. After commit, `notify_signup_changed` fires once (from the inner service), cacheops invalidations fire.

### Idempotency

Re-submitting with `intent: 'rsvp'` while already actively signed up → 400. Frontend doesn't dedupe — submit button is disabled while pending; page reads from invalidated queries after success.

### Race with Discord

`process_rsvp` is idempotent on "active signup exists." Web mutation handles 400 by showing the server's error message via toast.

## Error Handling

### Server-side error shape

All failures return `400` with `{"error": "<human-readable message>"}`.

### Client-side display

- **Validation errors before submit** (zod): inline `<FormMessage>`. Modal stays open; no toast.
- **Submit failure**: `toast.error(extractApiError(err))`; modal stays open; submit re-enables.
- **Network failure**: same toast path.
- **Auth lapse**: 401 → existing axios interceptor handles re-auth.
- **Event state changed mid-fill**: 400 with the existing wording; toast; user closes the modal.

### Skip-the-form path errors

400 on the fast path triggers a re-fetch of `useEvent` + `useUserDotaProfile`, then re-evaluates the gap. If the gap is now non-empty, the modal opens with the missing fields. Otherwise a toast surfaces the error.

### Atomicity

`apply_signup_input` and the chosen signup-creation function run inside a single `@transaction.atomic` block. If the second step raises, the profile write rolls back and the registered `invalidate_after_commit` / `notify_signup_changed` callbacks are *not* fired.

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

- `apply_signup_input` writes each field correctly (parametrized).
- Empty patch is a no-op.
- Disallowed `rank_status` raises `DjangoValidationError` with `code="rank_status_disallowed"` and the exact message from the vocabulary table.
- Positions outside `{1..5}` raise.
- Screenshot URL shape + extension allowlist.
- Duplicate Friend ID across `OrgUser`s in the same org raises with `code="duplicate_friend_id"` and the verbatim message including the `https://dota.kettle.sh` URL.
- **Multi-call partial-patch contract** — call `apply_signup_input` 4 times in sequence with different patch slices (rank_status, then positions, then medal, then screenshot); final profile state matches all writes; each call commits independently outside any enclosing transaction.
- **Cache invalidation** — patch `events.services.invalidate_after_commit` (the import in `services.py:10`, not the function in `app.cache_utils`) and assert it was called with `(profile, org_user, event)`.
- **Rollback case** — wrap in `self.captureOnCommitCallbacks(execute=False)` (the pattern at `test_discord_wiring.py:22+`); raise inside the atomic block; assert the captured callback list is empty *executed* (or use `execute=True` after rollback to confirm `cacheops.invalidate_obj` was not called — `call_count == 0` on the inner cacheops spy).
- Idempotent on retry (apply same patch twice, no spurious DB writes).

### Backend API tests

New file: `backend/events/tests/test_signup_endpoint.py`.

- Unauthenticated → 401.
- Event not in `SIGNUPS_OPEN` → 400.
- Empty `profile` patch + complete profile → creates signup; status reflects auto-approve / pending-approval / waitlist correctly.
- Empty `profile` patch + incomplete profile → endpoint accepts the request and writes whatever is in the patch (i.e., nothing). Hard policy gates inside `process_rsvp` (screenshot required + missing, `min_mmr` floor) still surface as 400. Soft completeness gates (Friend ID present, positions set, medal chosen) are **not** server-enforced; client-side zod is the only gate.
- `intent: 'tentative'` → creates tentative signup; duplicate tentative → 400.
- `intent: 'rsvp'` with full profile patch → profile fields persist AND signup is created (one transaction).
- Profile patch fails validation → no signup created (assert no `EventSignup` row).
- `process_rsvp` fails (e.g., `min_mmr` floor) → no profile write committed (use `TransactionTestCase` so the rollback boundary is real).
- `OrgUser` is created on first signup for a user not yet in the org.
- `notify_signup_changed` fires once after commit. Use `self.captureOnCommitCallbacks(execute=True)` and assert the callback list contains exactly one `notify_signup_changed` invocation. (The endpoint relies on `process_rsvp`/`create_tentative_signup` to register it; this test pins that the endpoint does not double-register.)
- Discord-initiated signup followed by web-initiated signup → idempotent; second returns 400. Use `TransactionTestCase` so commits are visible across "actors."
- New: `resolve_or_create_org_user` standalone test — creates `OrgUser` on first call, reuses on second; verifies parity with `_get_org_user` and `staff_add_signup`.

### Backend Discord regression tests

- `backend/discordbot/tests/test_components.py` — exercises `PositionConfirmButton`, `StarSelect`, `BattleCupTierSelect`, `ScreenshotUploadModal` callbacks directly. Add assertions that each callback now calls `apply_signup_input(...)` with the expected patch slice. Spy target: patch `events.discord.handlers.apply_signup_input` (the namespace where the adapter imports it), not `events.services.apply_signup_input`.
- `backend/events/tests/test_signup_interactions.py` — assert `handle_signup_modal_submit` calls `apply_signup_input` with the full modal patch.
- `backend/events/tests/test_reaction_signup.py` — verified to NOT touch profile fields. Smoke test only: confirm the reaction-driven path still creates an `EventSignup` after the refactor; no `apply_signup_input` spy needed.
- `backend/events/tests/test_discord_integration.py` — end-to-end Discord flow continues to pass; integration regression catcher.
- New: triggering a `DjangoValidationError` from `apply_signup_input` (e.g., disallowed rank_status) results in the adapter sending the exact ephemeral message from the vocabulary table — assert the rendered string equals the expected text. This pins error-text preservation.

### Frontend unit tests (Vitest)

Stack: `@testing-library/react` for component tests, `renderHook` for hooks, a `QueryClientProvider` test-utility wrapper, and MSW for HTTP mocking.

- `evaluateSignupGap(event, profile)` helper: parametrize over the full event-config × profile-completeness matrix, including the universal Friend-ID gate for non-Dota games (Deadlock event, no Friend ID on profile → returns `['friend_id']`).
- `toPatch(values, profile)` mapper: omits unchanged fields; includes only changed.
- `signupPatchSchema` builder: parametrized over event-config flags, asserts the right Zod fields are required vs optional.
- `EventSignupModal` component: render with various `event` + `profile` combinations, assert the right sections are visible/hidden and the right testids are present.
- `useUserDotaProfile()` hook: assert `initialData` is honored, that `staleTime` works, that mutations invalidate the key.
- Stale-defense scenario: render `event.tsx`, simulate a profile updated in another tab via a manual `queryClient.setQueryData`, click Sign Up, assert the gap evaluation uses the freshest data.

### Frontend E2E (Playwright)

New spec file: `frontend/tests/playwright/e2e/16-events/12-event-signup-form.spec.ts` (the next free numeric prefix; `09`, `10`, `11` are taken).

Direct API calls in tests use `postWithCsrf` against the new `/signup/` endpoint.

**Login fixtures.** Today's `loginEventPlayer` fixture uses `event_player_1`, who is populated by `populate_events_data` (`backend/tests/populate/events.py:130-136`) with a *complete* dota profile (Legend 3, active rank, screenshot). This means:

- `loginEventPlayer` is treated as **the complete-profile fixture** — used for the fast-path test. No new fixture file needed; the existing one fits.
- A new `loginEventPlayerNoProfile` fixture is added, backed by a new `event_player_no_profile` user the populate helper creates without any `PlayerDotaProfile`.

This avoids breaking the existing tests at `01-smoke`, `03-roll-call`, `04-discord-integration`, `05-signup-management`, `06-full-lifecycle` which all rely on `event_player_1`'s complete-profile state.

Cases:

- **Happy path: complete profile.** `loginEventPlayer` → click Sign Up on an event with no screenshot requirement → assert no modal mounts → toast → user appears in Signups tab.
- **Happy path: incomplete profile, all sections.** `loginEventPlayerNoProfile` → click Sign Up → modal opens with Friend ID + Rank Status + Positions + Rank Detail visible → fill all fields → submit → modal closes, toast, user appears in Signups tab.
- **Conditional reveal.** Pick `rank_status="never"` → assert Battle Cup Tier select appears, Medal/Star do not.
- **Screenshot required.** Event with `discord_require_rank_screenshot=true` → modal includes screenshot URL input → bad URL shows inline error → good imgur URL submits.
- **Tentative path.** Click Tentative → same modal but title reads "Mark Tentative for X" and submit reads "Mark Tentative" → submit creates a tentative signup → user appears in Tentative tab.
- **Allow flags filter rank-status.** Event with `allow_active_mmr=false` → only "previous" and "never" radios render.
- **Friend ID universal-across-game-types.** Deadlock event with `require_steam_id=true` and a user whose profile has no Friend ID → click Sign Up opens the modal with only the Friend ID section visible (no positions/rank). Requires a Deadlock event in the populate set (see "Test data" below).
- **Upgrade tentative to RSVP.** Sign up as Tentative → click the Sign Up upgrade button → assert the same gap-evaluation runs (modal opens for incomplete profile, fast path for complete profile) → resulting status is `rsvp`-equivalent.
- **Mobile viewport.** Set `page.setViewportSize({ width: 375, height: 812 })` (matches commit `99217b1c` pattern at `02-create-event.spec.ts:244-246`) and use the `MobileNavDropdown` flow to navigate to the event. Open the form via the mobile-rendered Sign Up button. Assert the form is rendered as a `<Sheet>` with sticky submit, fields stack, no horizontal scroll. Do **not** use Playwright's `devices['iPhone 14']`.

### `data-testid` inventory

Every testid used by the spec or by existing code that touches this surface:

- `event-signup-btn`, `event-tentative-btn` (existing; preserve).
- `event-signup-modal` (modal root).
- `event-signup-submit-btn`, `event-signup-cancel-btn`.
- `event-signup-error` (error surface inside the modal).
- `signup-friend-id`, `signup-rank-status`, `signup-positions`, `signup-rank-medal`, `signup-rank-star`, `signup-battlecup-tier`, `signup-screenshot-url`.
- `signup-prefilled-summary-friend-id`, `signup-prefilled-summary-rank-status`, `signup-prefilled-summary-positions`, `signup-prefilled-summary-rank-detail`, `signup-prefilled-summary-screenshot` (one per collapsed `<Collapsible>`).
- `event-upgrade-rsvp-btn`, `event-cancel-rsvp-btn`, `event-cancel-tentative-btn`, `event-reinstate-btn` (existing; preserve).

### Schema-drift snapshot

`backend/app/tests/test_schema_drift.py` snapshot regenerated. Spec adds an explicit assertion that `/api/events/{id}/signup/` exists in the snapshot. Removed: `/rsvp/`, `/tentative/`.

### Test data — populate helper

New helper registered in `backend/tests/populate/__init__.py::POPULATE_FUNCTIONS` (and exported in `__all__`). Reuses the existing org/league fixtures — `populate_events_data` (org 7 / league 7 / `event_player_1` per the `testing` skill's feature-isolation rule).

Adds:

- `event_player_no_profile` — a new user in org 7 with **no** `PlayerDotaProfile` row. Backs the `loginEventPlayerNoProfile` Playwright fixture.
- One Dota 2 event with `discord_require_rank_screenshot=true`.
- One Dota 2 event without screenshot requirements.
- One **Deadlock** event with `require_steam_id=true` (for the Friend-ID-universal-across-game-types Playwright case).

`event_player_1` is left untouched; existing tests rely on its complete-profile state. Idempotent on re-run (per testing skill rules).

## Rollout

- Single PR.
- Schema-drift snapshot regenerated in the same PR.
- Migration of existing `/rsvp/` and `/tentative/` test callers (backend `test_api.py`, Playwright `01-smoke.spec.ts`, `03-roll-call.spec.ts`, `04-discord-integration.spec.ts`) ships in the same PR — partial migration leaves CI red.
- New Playwright fixture `loginEventPlayerNoProfile` and the corresponding `event_player_no_profile` populate addition ship in the same PR.
- Precursor commit (optional) adding `<RadioGroup>` via `npx shadcn@latest add radio-group` if the PR is too large to combine — otherwise included.
- No production data migrations; `cacheops` config is unchanged.
- Discord users see no change (vocabulary table preserves wording exactly). Web users see the new modal/form.
- Rollback: revert the PR. Old endpoints come back along with the old hooks.

## Out-of-scope follow-ups

- **Deadlock rich form.** Mirror this design with the simpler Deadlock field set (rank text + last-played date).
- **Real file-upload pipeline.** Replace URL-paste with multipart upload to Cloudflare R2, presigned URLs for client-direct uploads. Migrate Discord's `URLField` to write R2 URLs too.
- **MMR auto-derivation.** Pre-fill `OrgUser.mmr` from medal+star using a published mapping table; admin retains override via `MmrApprovalModal`.
- **Profile editor.** A dedicated `/profile/dota` page so users can update positions / rank without going through an event signup. Builds on `useUserDotaProfile()` introduced here.
- **Brand token additions.** A precursor brand-token PR that adds `position-role-*` color tokens, per-medal palettes, and a neon-hairline divider utility — would unlock a richer visual treatment for the position pills, medal pills, and section dividers in this surface.
- **Discord `notify_signup_changed` deduplication.** The pre-existing double-fire (handlers.py calls + services.py on_commit) can be consolidated in a focused PR after this lands.
