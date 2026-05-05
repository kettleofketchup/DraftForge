# Event Signup Form — Design Spec

**Date:** 2026-05-05
**Status:** Draft (pending implementation plan)
**Branch (when implemented):** `feat/event-signup-form`

## Context

Today, signing up for an event has two surfaces with very different fidelity:

- **Discord** — clicking the green **Sign Up** button on an event embed opens a rich, multi-step flow that collects Steam Friend ID, preferred Dota 2 positions, rank status (active / previous / never), medal + star or Battle Cup tier, and (when the event requires it) an MMR or Battle Cup screenshot. Profile data is persisted to the user's `PlayerDotaProfile` and reused on the next event. Implementation lives in `backend/discordbot/components.py` and `backend/events/discord/handlers.py`.
- **Website** — clicking **Sign Up** on `/events/<id>` opens a single confirm dialog ("RSVP for Event?") and fires `POST /api/events/<id>/rsvp/`. No data collection. Admins fill in the player's MMR after the fact via the existing `MmrApprovalModal`.

The asymmetry is a real product problem: web users skip the data-gathering step that Discord users go through, which means the admin approval queue carries unequal load and per-event signup-policy flags (`min_mmr`, `discord_require_rank_screenshot`, etc.) are effectively unenforced for web signups. This spec brings the website to data parity with Discord.

## Goals

- Web signup collects the same player data Discord collects, gated by the same per-event `event_config` flags (`require_steam_id`, `require_rank_screenshot`, `require_battlecup_screenshot`, `min_mmr`, `allow_active_mmr`, `allow_previous_rank`, `allow_battlecup_rating`).
- A web-initiated signup ends up in the database **indistinguishable** from a Discord-initiated one — same `EventSignup`, same `PlayerDotaProfile` writes, same downstream admin flow, same `process_rsvp` business logic.
- Repeat web signups respect the user's prior profile data: nothing-missing-no-form fast path mirrors Discord's instant signup.
- Both **Sign Up** and **Tentative** buttons use the same form; only the resulting `EventSignup.status` and submit-button label differ.
- A single canonical signup-input service is shared between Discord and web — no duplicated business logic.
- Brand-compliant per `docs/THEMING-GUIDE.md` (brand button system, `bg-base-*`, no raw `<button>`).

## Non-goals

- **Deadlock.** The Discord modal supports a Deadlock variant (free-text rank + last-played date). The Friend ID gate applies to all game types, but the rich Dota 2 form (positions, rank-status branch, medal/star/Battle Cup, screenshot) is **not** mirrored for Deadlock in this iteration. Deadlock signups continue through Discord; a Deadlock follow-up can copy this design with minor changes.
- **File upload pipeline.** The codebase has no `MEDIA_ROOT`, `STORAGES`, or S3 client. Screenshots are URL-paste only (imgur or any `https?://…`), matching Discord's existing fallback. A real upload pipeline is a separable project.
- **Multi-step wizard.** Discord's multi-step flow exists because of platform component limits we don't have on the web. The web form is one cohesive modal with conditional sections; no artificial step-throughs.
- **MMR auto-derivation from medal+star.** Selecting "Crusader 3" does not auto-fill numeric MMR. Admins continue to set the actual numeric MMR via `MmrApprovalModal` after signup. Mirrors current Discord behavior.
- **Discord-side changes other than the shared-service refactor.** No new Discord buttons, modal layout changes, or embed-content changes.

## Constraints

- Backend: Django + DRF + Pydantic schemas; cacheops invalidation discipline (model-level cache, see `app/settings.py` `CACHEOPS` block).
- Frontend: React 19, react-router (SSR + client), TanStack Query, react-hook-form + zod, shadcn-derived `FormField` stack, brand button system from `frontend/app/components/ui/buttons/`.
- Testing: backend tests via `just test::run`, Playwright E2E via `just test::pw::*`, populate-helper system per `testing` skill.
- Brand: `docs/THEMING-GUIDE.md` is canon. All UI must pass the `/brand` review.
- Existing rich Discord signup flow must continue to work without behavior changes after the shared-service extraction (commit `33bacad4` shipped just days ago — minimize regression risk).

## Architecture Overview

A web user clicks **Sign Up** or **Tentative** on `/events/<id>`. The frontend evaluates the user's existing `dota_profile` (already returned by the event SSR/loader payload) against the event's `event_config` flags. Two paths:

- **Nothing missing** → button click fires `POST /api/events/<id>/signup/` immediately with `{ intent }` and an empty profile patch. No modal, no extra render.
- **Something missing** → opens `EventSignupModal`, prefilled with whatever exists. User fills the gaps, submits the same endpoint with the patched profile fields.

The new endpoint lives on `EventViewSet` as a DRF action (sibling to `rsvp`, `tentative`, `admin_signup`). Its body is a thin orchestration: validate input → call shared service → return `EventSignupSerializer`.

The shared service module is the contract between Discord and web. The current Discord-only helpers in `events/discord/handlers.py` (`_save_dota_profile`, the position writes inside `PositionConfirmButton.callback`, the screenshot URL writes inside `handle_screenshot_upload`) are extracted into `events/services.py` as plain functions taking a `CustomUser` and a profile patch dict. Discord handlers become call-sites that build the same dict from interaction values and forward it. Web endpoint builds the same dict from the validated request body. Single canonical write path.

```
                       ┌──────────────────────────┐
   Discord interaction │  events/discord/handlers │
   (button → modal →   │  - build patch dict      │
    select → submit)   │  - call shared services  │
                       └─────────┬────────────────┘
                                 │
                                 ▼
                       ┌──────────────────────────┐
                       │  events/services.py      │
                       │  - apply_signup_input()  │
                       │  - process_rsvp()        │
                       │  - create_tentative()    │
                       └─────────▲────────────────┘
                                 │
                       ┌─────────┴────────────────┐
   POST /api/events/   │  EventViewSet.signup     │
   <id>/signup/        │  - validate body         │
                       │  - call shared services  │
                       └──────────────────────────┘
```

## Backend

### Shared service: `apply_signup_input`

New function in `events/services.py`:

```python
def apply_signup_input(*, user: CustomUser, event: Event, patch: SignupInputPatch) -> PlayerDotaProfile:
    """Idempotently write any provided fields onto the user's PlayerDotaProfile.

    Fields not in `patch` are not touched. Validates against `event` config flags
    (positions allowed, rank_status allowed, screenshot URL shape) and raises
    ValidationError on policy violations. Invalidates cacheops on save.
    """
```

`SignupInputPatch` is a typed structure (Pydantic model in `events/schemas.py`) with all-optional fields:

| Field                    | Type                                       | Notes                                            |
| ------------------------ | ------------------------------------------ | ------------------------------------------------ |
| `unverified_friend_id`   | `str` (max 20)                             | Numeric not enforced; matches Discord laxity.    |
| `positions`              | `list[int]` ⊆ `{1,2,3,4,5}`                | Stored as five booleans on `PlayerDotaProfile`.  |
| `rank_status`            | `Literal["active", "previous", "never"]`   | Must be allowed by event config.                 |
| `rank_medal`             | `str` (e.g., `"Crusader 3"`, `"Immortal"`) | Required at completion when status ∈ active/prev.|
| `battle_cup_tier`        | `int` ∈ `{1..8}`                           | Required at completion when status = `never`.   |
| `rank_screenshot`        | `str` (URL, max URLField length)           | `https?://…` shape check.                        |
| `battlecup_screenshot`   | `str` (URL)                                | `https?://…` shape check.                        |

Optionality lets the same function serve "partial fill from Discord modal step" and "complete fill from web form" without branching.

Validation rules embedded in this function (same rules Discord enforces today, surfaced once):

- `rank_status` must satisfy `event.discord_allow_active_mmr` / `discord_allow_previous_rank` / `discord_allow_battlecup_rating`.
- Positions deduped, all in `{1..5}`; out of range → raise.
- Screenshot URL: `https?://…` shape check, length ≤ `URLField.max_length`.

The function does **not** perform "completeness" gating itself — that lives in `process_rsvp`'s existing `min_mmr` / screenshot-required / auto-approve checks (already battle-tested via Discord).

### New endpoint: `POST /api/events/<id>/signup/`

`@action(detail=True, methods=["post"])` on `EventViewSet`. Request body:

```json
{
  "intent": "rsvp" | "tentative",
  "profile": { /* SignupInputPatch fields, all optional */ }
}
```

Response: `EventSignupSerializer` payload (201 on creation), same shape `rsvp` and `tentative` already return.

Body flow:

1. `IsAuthenticated` permission (matches `rsvp`).
2. Event state check: `event.state == SIGNUPS_OPEN`. Wrong state → 400 `{"error": "Event is not accepting signups"}`.
3. Body validation via Pydantic: unknown fields rejected; `intent` required; `profile` defaults to `{}`.
4. `@transaction.atomic`:
   - `apply_signup_input(user=request.user, event=event, patch=body.profile)`.
   - Branch on `intent`:
     - `"rsvp"` → `process_rsvp(event, request.user)` (existing function — runs screenshot / `min_mmr` / auto-approve / waitlist logic and creates the `EventSignup`).
     - `"tentative"` → new `create_tentative_signup(event, request.user)` service function (extracted from inline view code at `views.py:496–524`). Same duplicate-signup checks, same cancelled-row cleanup, returns the new signup row.
5. Return `EventSignupSerializer(signup).data` with 201.

Errors map to 400 with `{"error": "..."}` (matches the existing `rsvp` action's error shape).

### Discord refactor

`events/discord/handlers.py::handle_signup_modal_submit` and the position / medal / star / battle-cup-tier / screenshot callbacks stop writing fields directly. Each one builds its slice of the patch dict and calls `apply_signup_input(...)`. `_save_dota_profile` is deleted; its callers either inline the patch-building or call the shared function. `handle_screenshot_upload` builds `{"rank_screenshot": url}` or `{"battlecup_screenshot": url}` and forwards.

Net code change in Discord land: smaller, not larger. No behavior change there — the Discord tests already cover those handlers and continue to pass.

### Tentative as a service

The current `tentative` DRF action (`views.py:486–525`) inlines its own logic: state check, existing-signup check, cancelled-row cleanup, `EventSignup.objects.create(...)`, cache invalidation. We extract this into `events/services.py::create_tentative_signup(event, user) -> EventSignup`.

### Removed endpoints

The old `POST /api/events/<id>/rsvp/` and `POST /api/events/<id>/tentative/` actions on `EventViewSet` are **deleted**. Their only callers are the frontend hooks (`useRsvpMutation`, `useTentativeMutation`) which are also deleted in this change. Discord does not use these HTTP endpoints — it calls the service-layer functions (`process_rsvp`, `create_tentative_signup`) via Python imports. Replacement is the single new `POST /api/events/<id>/signup/` endpoint with `intent` discriminator. Keeping the old endpoints "for backwards compatibility" would violate the codebase's no-dead-code policy (`CLAUDE.md`: don't keep shims for callers that don't exist).

### Migrations

None. The schema already supports everything; we're only changing *who* writes it.

## Frontend

### `EventSignupModal` component

New file: `frontend/app/components/events/EventSignupModal.tsx`. Wired into `frontend/app/routes/event.tsx` in place of the existing `ConfirmDialog` "RSVP for Event" branch.

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

**Conditional sections** (each its own subcomponent for unit-testability):

1. **Friend ID** (`FriendIdField`): visible iff `event.discord_require_steam_id && !profile?.unverified_friend_id`. Single text input via brand `FormField` + `Input`. `data-testid="signup-friend-id"`.
2. **Rank Status** (`RankStatusRadioGroup`): visible iff `!profile?.rank_status`. Three radio cards (`active` / `previous` / `never`) filtered by `event.discord_allow_active_mmr` / `allow_previous_rank` / `allow_battlecup_rating`. Same emoji + description shown in Discord. `data-testid="signup-rank-status"`.
3. **Positions** (`PositionPickerGrid`): visible iff Dota 2 game type AND `!hasAnyPosition(profile)`. Five toggle pills (1–5 with Discord's emoji and label). Five booleans on `PlayerDotaProfile` (same shape Discord writes after `PositionConfirmButton`). `data-testid="signup-positions"`.
4. **Rank Detail** (`RankDetailFields`):
   - When chosen status is `active` or `previous` → Medal `Select` (Herald → Immortal) + Star `Select` (1–5, hidden when medal is `Immortal`).
   - When `never` → Battle Cup Tier `Select` (1–8).
   `data-testid="signup-rank-medal"`, `signup-rank-star`, `signup-battlecup-tier`.
5. **Screenshot URL** (`ScreenshotUrlField`): visible iff event requires it for the chosen rank-status branch AND no existing URL on profile. Single text input plus a small helper block with copy "Upload your screenshot to imgur.com and paste the link here." Validated as `https?://…`. `data-testid="signup-screenshot-url"`.
6. **Submit row**: brand `PrimaryButton` (label = "Sign Up" or "Mark Tentative" based on intent) + brand `SecondaryButton` "Cancel". Loading state via existing button `loading` prop. Submit disabled until zod schema is valid for the visible fields.

### Form stack

Per the `zod-form-validation` skill: `react-hook-form` + `zodResolver`. Schema is built dynamically from `event.event_config` and the user's existing `profile` so only fields that need filling are validated. A `toPatch(values, profile)` mapper produces the request body, omitting any field that hasn't changed from the prefill.

### Skip-the-form fast path

Implemented in `event.tsx`, not in the modal. A pure helper `evaluateSignupGap(event, profile)` returns either `'complete'` or a list of missing-section keys.

```ts
function evaluateSignupGap(event: EventType, profile: DotaProfileData | null): 'complete' | string[] {
  const missing: string[] = [];
  if (event.discord_require_steam_id && !profile?.unverified_friend_id) missing.push('friend_id');
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

### Mutation wiring

New `useSignupMutation(eventId)` in `frontend/app/hooks/useEvent.ts`, parallel to the existing `useRsvpMutation` and `useTentativeMutation`. Posts to the new endpoint, invalidates `['event-signups', eventId]` and the event detail query on success — same invalidation set the existing mutations use. The old `useRsvpMutation` / `useTentativeMutation` and the `ConfirmDialog` "RSVP for Event" code path are deleted; the buttons go through the new mutation only.

### Brand compliance

This is a `/brand` review surface. The implementation must satisfy:

- Buttons: `PrimaryButton`, `SecondaryButton`, `DestructiveButton` only — no raw `<button>` or `<Button>`.
- Surfaces: `bg-base-*` scale and tokens from `frontend/app/app.css`. No `bg-slate-*`, no inline violet/indigo hex, no `style={{}}`.
- Form pieces: existing `FormField` / `FormLabel` / `FormDescription` / `FormMessage` from the shadcn-derived form module — same set used in `EditEventModal.tsx` and `CreateEventModal.tsx`.
- `cn()` for class composition; no template-string class concatenation.
- Mobile-first: stacked layout by default, two-column reveals only at `md:` for the position / medal+star groupings; touch targets `min-h-11`.

## Data Flow & Validation

### SSR / loader path

No changes. The event SSR loader (`/events/<id>/ssr/`) already returns `dota_profile` for the current user inside `EventSignupSerializer.user_data` (line 439 of `serializers.py`). The event detail itself already exposes the `discord_require_*` and `discord_allow_*` flags. `event.tsx` already pulls all of this via `useEvent(id)` and `useEventSignups(id)`.

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

Any field the user didn't change is omitted (the `toPatch(values, profile)` mapper diffs against the profile prefill). Empty `profile: {}` is the fast-path call.

### Server-side validation order

1. **Auth gate** — `IsAuthenticated`.
2. **Event state** — `event.state == SIGNUPS_OPEN`. Wrong state → 400 `{"error": "Event is not accepting signups"}`.
3. **Body shape** — Pydantic validates the patch dict. Unknown fields rejected.
4. **Policy validation in `apply_signup_input`** — rank-status allowed, position range, screenshot URL shape.
5. **Profile write** — atomic save inside a transaction; cacheops invalidation via `invalidate_obj(profile)`.
6. **Intent branch** — `process_rsvp` or `create_tentative_signup`.
7. **Response** — `EventSignupSerializer(signup).data`, 201 on creation.

### Idempotency

Re-submitting with `intent: 'rsvp'` while already actively signed up → 400 (matches existing behavior; `process_rsvp` already enforces this). The frontend doesn't need its own dedupe — the modal's submit button is disabled while the mutation is pending, and the page reads from the freshly invalidated query after success.

### Cache invalidation

Existing `invalidate_after_commit(signup, event)` call inside the signup-creation services already covers the signup list. Profile-side cacheops invalidation happens inside `apply_signup_input`. No new cache plumbing.

### Race with Discord

A user could click Sign Up on the website while their Discord modal is half-open. `process_rsvp` is already idempotent on "active signup exists" — the second submit (whichever side) returns the existing signup or a 400 "already signed up" error. The web mutation handles 400 by showing the server's error message via toast, no special-case code.

## Error Handling

### Server-side error shape

All failures return `400` with `{"error": "<human-readable message>"}` — same shape `rsvp` and `tentative` already use.

### Client-side display

- **Validation errors before submit** (zod): inline `FormMessage` under the offending field. Modal stays open; no toast.
- **Submit failure**: `toast.error(extractApiError(err))`; modal stays open; submit re-enables for retry.
- **Network failure**: same toast path; `extractApiError` returns "Something went wrong" if the response is unparseable.
- **Auth lapse**: 401 → existing axios interceptor handles re-auth.
- **Event state changed mid-fill**: 400 with the existing wording; toast; user closes the modal.

### Skip-the-form path errors

Same toast pipeline; just no modal to leave open. If the immediate fast-path call returns 400 (cached profile said "complete" but server disagrees — defense in depth), re-fetch the event + profile, re-evaluate the gap, and either show the modal with the missing field highlighted or surface a toast and stop.

### Atomicity

`apply_signup_input` and the chosen signup-creation function run inside a single `@transaction.atomic` block on the action method. If the second step raises, the profile write rolls back. The user sees one error and one consistent state — same as Discord today.

### Logging

Match the existing `logger.info` / `logger.warning` calls on the `rsvp` action (lines 461–490 of `views.py`):

```
INFO  signup request: user=<pk>, event=<pk>, intent=rsvp, fields=[friend_id, positions, rank_status, rank_medal]
INFO  signup success: user=<pk>, event=<pk>, status=rsvp
WARN  signup rejected: user=<pk>, event=<pk>, reason="<error message>"
```

Logged via the `logging` skill conventions (`system=events`, `subsystem=signup`).

## Testing

### Backend unit tests

New file: `backend/events/tests/test_signup_input.py`.

- `apply_signup_input` writes each field correctly (parametrized over Friend ID, positions, rank-status branches, medal/star, battle cup tier, both screenshot URLs).
- Empty patch is a no-op.
- Disallowed `rank_status` raises ValidationError.
- Positions outside `{1..5}` raise; deduped on save.
- Screenshot URL shape validation.
- Cacheops invalidation fires (assert via spy on `invalidate_obj`).
- Idempotent on retry.

### Backend API tests

New file: `backend/events/tests/test_signup_endpoint.py`.

- Unauthenticated → 401.
- Event not in `SIGNUPS_OPEN` → 400.
- Empty `profile` patch + complete profile → creates signup; status reflects auto-approve / pending-approval / waitlist correctly.
- Empty `profile` patch + incomplete profile → endpoint accepts the request and writes whatever is in the patch (i.e., nothing). Hard policy gates inside `process_rsvp` (screenshot required + missing, `min_mmr` floor) still surface as 400. Soft completeness gates (Friend ID present, positions set, medal chosen) are **not** server-enforced — they're enforced client-side via zod, matching Discord's `required=True` modal field semantics. Test pins this distinction: a soft-incomplete profile + empty patch is a successful signup if no hard gate fails.
- `intent: 'tentative'` → creates tentative signup; duplicate tentative → 400.
- `intent: 'rsvp'` with full profile patch → profile fields persist AND signup is created (one transaction).
- Profile patch fails validation → no signup created (assert no `EventSignup` row).
- `process_rsvp` fails (e.g., `min_mmr` floor) → no profile write committed (transactional rollback test).
- Discord-initiated signup followed by web-initiated signup → idempotent; second returns 400 "already signed up."

### Backend Discord regression tests

No new files. Existing `test_signup_interactions.py`, `test_reaction_signup.py`, `test_discord_integration.py` cover the Discord adapter and continue to pass after the refactor. Add one assertion in `test_signup_interactions.py`: the Discord callback now goes through `apply_signup_input` (spy on the function, assert called once with the expected patch dict).

### Frontend unit tests (Vitest)

- `evaluateSignupGap(event, profile)` helper: parametrize over the full `event_config` × `profile`-completeness matrix. This is the spec we lock down — it's the brain of skip-the-form.
- `toPatch(values, profile)` mapper: omits unchanged fields; includes only changed.
- Schema builder: parametrized over event-config flags asserts the right Zod fields are required vs optional.

### Frontend E2E (Playwright)

New spec: `frontend/e2e/specs/event-signup-form.spec.ts` per the `testing` skill.

- **Happy path: complete profile.** Login as a user with a complete dota profile → click Sign Up on an event with no screenshot requirement → assert no modal mounts (`expect(getByTestId('event-signup-modal')).not.toBeVisible()`) → toast → user appears in Signups tab.
- **Happy path: incomplete profile, all sections.** Login as a fresh user with no `dota_profile` → click Sign Up → modal opens with Friend ID + Rank Status + Positions + Rank Detail visible → fill all fields → submit → modal closes, toast, user appears in Signups tab.
- **Conditional reveal.** Pick `rank_status="never"` → assert Battle Cup Tier select appears, Medal/Star do not.
- **Screenshot required.** Event with `discord_require_rank_screenshot=true` → modal includes screenshot URL input → bad URL shows inline error → good imgur URL submits.
- **Tentative path.** Click Tentative button → same modal but submit label reads "Mark Tentative" → submit creates a tentative signup → user appears in Tentative tab.
- **Allow flags filter rank-status.** Event with `allow_active_mmr=false` → only "previous" and "never" radios render.
- **Mobile viewport.** Run a subset under iPhone 14 device — modal opens, sections stack, submit reachable without horizontal scroll.

### Test data

New populate helper `populate_event_signup_form_fixtures()` in the testing populate registry (per the `testing` skill): creates one event-with-screenshots-required, one event-without, one user with empty profile, one user with complete profile. Idempotent. No raw DB writes outside the populate system.

## Rollout

- Single PR. Feature flag not needed: the new modal replaces the existing confirm dialog wholesale; behavior change is desirable on first deploy.
- Deploy backend before frontend would be safer (new endpoint exists before the UI calls it), but in practice these ship together since the build is one image; rollback story is "revert PR."
- `cacheops` is not affected (no model schema changes).
- No Discord-side changes ship to users — the refactor is internal.

## Out-of-scope follow-ups

- **Deadlock signup form.** Mirror this design with the simpler Deadlock field set (Friend ID + free-text rank + last-played date).
- **Real file-upload pipeline.** Replace URL-paste with multipart upload to Cloudflare R2 (already used for static assets), serving presigned URLs for client-direct uploads. Migrate Discord's `URLField` to write R2 URLs too for consistency.
- **MMR auto-derivation.** Pre-fill `OrgUser.mmr` from medal+star using a published mapping table; admin retains override via `MmrApprovalModal`.
- **Profile editor.** A dedicated `/profile/dota` page so users can update positions / rank without going through an event signup.
