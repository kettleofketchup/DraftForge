# Event System

Schedule recurring events with Discord integration, automated signups, and tournament auto-creation.

## Overview

Organizations create one-off or recurring events that automatically generate tournaments. Players RSVP, admins approve/confirm attendance via roll call, and tournaments start with the confirmed roster.

- **Recurring event series** with configurable frequency (daily, weekly, bi-weekly, monthly)
- **Discord integration** — scheduled events, signup sync, channel announcements, attendance confirmation
- **Organization event defaults** — pre-fill event config from org-level settings
- **Repeater subscriptions** — users subscribe to get notified when new events are created
- **Waitlist** with automatic promotion when slots open
- **Roll call** page for confirming player attendance before tournament start
- **End time, Complete and host/helpers** for multi-day events, closing an event and crediting who ran it

<figure markdown="span">
  ![Event Creation Demo](https://assets.kettle.sh/draftforge/gifs/event_creation.gif){ width="400" }
  <figcaption>Creating a recurring weekly event with Discord integration</figcaption>
</figure>

[:material-play-circle: Watch event creation demo](https://assets.kettle.sh/draftforge/videos/event_creation.webm)

---

## Supported Games

Events are typed by `event.game_type` (set at event creation, immutable thereafter):

| Game | `game_type` | Profile model | Web signup | Discord signup |
|---|---|---|---|---|
| Dota 2 | `1` | `PlayerDotaProfile` | ✓ (full modal) | ✓ |
| Deadlock | `2` | `PlayerDeadlockProfile` | partial — Friend ID only today | ✓ (full modal) |

The signup-modal field set is selected by `game_type`. Most rank/skill fields are **Dota-only**:

- **Profile fields** (Dota-only): `positions` (carry/mid/offlane/soft_support/hard_support priorities 0–5), `rank_status` (active / previous / never), `rank_medal` (e.g. "Legend 4"), `battle_cup_tier` (1–8), `rank_screenshot`, `battlecup_screenshot`.
- **Profile fields** (Deadlock-only): `rank` (free-text), `rank_date`.
- **Profile fields** (shared): `unverified_friend_id` (mirrored to `CustomUser.steam_account_id` first-write-wins on approve).
- **Event-config flags** (Dota-only): `allow_active_mmr`, `allow_previous_rank`, `allow_battlecup_rating`, `min_mmr`, `require_mmr_verified`, `discord_require_rank_screenshot`, `discord_require_battlecup_screenshot`.

!!! note "Deadlock web parity"
    The web signup modal currently only renders the optional Friend ID section for Deadlock events. The full Deadlock rank/date capture lives on the Discord side today (`PlayerDeadlockProfile` direct write). Web parity is tracked as a follow-up.

---

## Features

### Event Creation

Events are created from the organization page via a tabbed modal:

- **Event tab** — name, tournament config (game, draft type, bracket), schedule
- **Discord tab** — scheduled event creation, signup sync, channel picker, reminders
- **Recurring toggle** — converts to an EventRepeater with frequency/day/time

Recurring events automatically generate individual events based on the schedule, each inheriting the repeater's configuration.

For Dota 2 the configuration includes the hosted-lobby settings (off, manual or automatic lobbies; match start; region; the lobby info DM) and the **lobby password**: fixed (typed by staff on the series or event) or random (generated once per event). Every lobby of an event uses its one password; registered players (approved or confirmed signups, or rostered on a team) see it on the event page ahead of time. Each event copies these settings onto its tournament. See [Dota 2 lobbies: Event lobby passwords](planned/dota-lobbies.md#event-lobby-passwords).

### Organization Event Defaults

Admins configure default settings per organization. When creating new events, the form pre-fills from these defaults — no need to re-enter Discord channels, tournament config, or approval settings each time.

### Extra Sessions on a Series

From a series page (`/event-series/{id}`) org staff can add an **extra session attached to the series** — one event scheduled outside the series' recurrence, at a time they pick. It is fully part of the series: it carries `event_repeater`, so it inherits the series' tournament template, signup rules and Discord config. Subscriber reminders, the Discord *Notify Me for Future Events* button and every other reminder work on it exactly as they do on a generated occurrence. The UI labels the button *Add one-off event* and badges the result **One-off**.

What sets it apart is `Event.is_off_schedule`, which `create_off_schedule_event` sets on the row. The flag means "attached to the series, but not produced by its schedule", and it keeps the series' realign and config cascade off the event (see [Event Reminder Scheduling](../architecture/event-reminder-scheduling.md#realign-on-edit)):

- Editing the series' day, time or frequency never deletes or moves it.
- Editing the series' name, tournament config or Discord settings never overwrites the values chosen for it.

Every config field on the create form is optional and prefilled from the series, so an untouched submit reproduces the series' own settings at the chosen instant. Two timestamps are rejected with `409 Conflict`: one that already has an event in this series, and one that is a real upcoming occurrence of the schedule. A past timestamp, or one past the series' `ends_at`, is a `400`.

!!! note "Not the same as a one-off event"
    Elsewhere on this page "one-off"/"single event" means an event created with **no** series — that is what `discord_signup_reminder` is rejected for. An extra session is the opposite case: it belongs to a series and is only off that series' *schedule*.

### Series Reactivation

Pausing a series (`is_active = false`) stops event generation. **Reactivate** turns it back on and realigns in one step, so a paused series doesn't come back with a mix of stale and fresh rows:

1. `is_active` is set back to `true`.
2. Upcoming events are realigned against the *current* schedule — rows that no longer match a scheduled occurrence (typically left behind by a schedule edit made while paused) are torn down, taking their Discord scheduled event with them, and the missing occurrences are generated.
3. Off-schedule extra sessions are left alone.

The response carries `created_count` plus a message that distinguishes "no new events were due" from "the series' end date has passed", so the page can say which of the two happened. A `PATCH` that flips `is_active` from `false` to `true` realigns identically — `is_active` is part of the schedule-change snapshot that `perform_update` compares.

While a series is paused, realign is skipped entirely rather than run against a schedule that generates nothing — otherwise it would simply delete the series' remaining events.

### Discord Integration

| Feature | Description |
|---------|-------------|
| Create scheduled event | Automatically creates a Discord scheduled event, only while the event's start time is in the future (Discord rejects past starts); once the start has passed, the Discord Tasks panel shows it as disabled and manual fire is refused |
| Synchronize signups | Keep website and Discord event signups in sync |
| Mark as interested | Players who sign up are marked interested on Discord |
| Signup channel | Post an embed to a channel for reaction-based signups |
| Pre-day announcement | Post a reminder in a channel before the event |
| Signup reminder | DM subscribers who haven't signed up (recurring series only) |
| Profile reminder | DM users to complete their profile (Steam ID, MMR) |
| Confirm attendance | Require Discord reply to confirm attendance on event day |
| Scheduled-event cleanup | Cancelling or deleting an event deletes its Discord scheduled event (`events.tasks.delete_discord_scheduled_event`), so nothing is left orphaned in the guild |

**Discord signup pipeline** (Dota events): clicking *Sign Up* either signs the user up directly (profile complete) or opens a modal with rank-status select → position select view → optional medal+star follow-up → optional screenshot upload. Each step routes through `events.services.apply_signup_input` — the **same service the web `/signup/` endpoint uses** — so the two paths converge on identical writes. Deadlock signups take a separate Discord-only branch that writes `PlayerDeadlockProfile.rank` directly.

### RSVP & Signups

Players RSVP from the event page (web) or via the Discord signup post. The signup flow respects event configuration:

- **Auto-approve** — signups go directly to Approved status
- **Manual approval** — admin reviews and approves each signup
- **Waitlist** — when max players is reached, new signups are waitlisted with position tracking
- **Re-RSVP** — cancelled signups can re-register

#### Web vs Discord parity

Both signup paths funnel through `apply_signup_input` and write the same per-org `PlayerDotaProfile` row, so the two surfaces are interchangeable for Dota events. The table below shows where each field is captured and which model it lands on.

| Field | Web (`/signup/`) | Discord modal | Storage |
|---|---|---|---|
| `unverified_friend_id` | ✓ when `require_steam_id` | ✓ modal text input | `PlayerDotaProfile.unverified_friend_id` (Dota) or `PlayerDeadlockProfile.unverified_friend_id`. First-write-wins mirror to `CustomUser.steam_account_id`. |
| `positions` (Dota) | ✓ priority dict 0–5 per role (PositionForm) | ✓ slot-ordered list (1st / 2nd / 3rd choice selects) | `PlayerDotaProfile.pos_1..5` booleans (derived) **and** `CustomUser.positions` PositionsModel (priorities 1–5). Web sends a literal dict; Discord's `list[int]` is mapped to priorities by slot index (1st pick → priority 1, 2nd → 2, capped at 5; earliest slot wins on duplicate role). |
| `rank_status` (Dota) | ✓ RankStatusRadioGroup | ✓ rank select | `PlayerDotaProfile.rank_status` |
| `rank_medal` (Dota) | ✓ medal+star → joined ("Legend 4") | ✓ MedalSelect + StarSelect follow-up | `PlayerDotaProfile.rank_medal` |
| `battle_cup_tier` (Dota) | ✓ when `rank_status="never"` | ✓ BattleCupTierSelect | `PlayerDotaProfile.battle_cup_tier` |
| `rank_screenshot` (Dota) | ✓ URL field, validated for `.png/.jpg/.jpeg/.webp` | ✓ Discord attachment URL | `PlayerDotaProfile.rank_screenshot`. Required only when `rank_status="active"` and the event sets `discord_require_rank_screenshot`. "I had an MMR" (previous) records the rank via medal+star without a screenshot. |
| `battlecup_screenshot` (Dota) | ✓ | ✓ | `PlayerDotaProfile.battlecup_screenshot` |
| `deadlock_rank` | **not yet** | ✓ modal text | `PlayerDeadlockProfile.rank` |
| `mmr` numeric (admin-only) | ✓ on approve (`mmr_override`) | ✓ on approve | `OrgUser.mmr`, `has_active_dota_mmr`, `dota_mmr_last_verified` — also emits an `OrgLog` `set_mmr` entry |

The endpoint is a single canonical action accepting `{intent, profile}`; the older `/rsvp/` and `/tentative/` actions have been removed.

#### Approve flow

Admin approve uses `POST /api/event-signups/{id}/approve/` with optional `{ "mmr": <int> }`. On approve:

- `EventSignup.status` → `approved`.
- If `mmr` is supplied, `OrgUser.mmr` is written and the OrgLog records `set_mmr`. An `OrgUser` row is created if missing.
- Friend ID is mirrored to `CustomUser.steam_account_id` if not yet set (first-write-wins).
- **Approve does NOT mutate positions.** The legacy behavior that flattened `pos_N` booleans into `priority=1` on `CustomUser.positions` at approve time has been removed — priorities now come exclusively from the signup write via `apply_signup_input`, which is authoritative. The per-org `PlayerDotaProfile.pos_N` booleans are the derived binary view for that event.

### Repeater Subscriptions

Users can subscribe to event repeaters (mail icon on repeater cards). Two distinct notifications hang off a series, and they reach different audiences:

| When | What is sent | Gated by |
|---|---|---|
| An event is created from the series | A **channel embed** announcing the new event | `EventRepeater.discord_notify_new_events`, then the event's `discord_announcement` **and** `discord_announcement_channel_id` |
| `discord_signup_reminder_hours` before the event | A **DM to each subscriber** who hasn't signed up yet | `discord_signup_reminder` (series only) |

Subscribing is what earns you the pre-event signup-reminder DM. The new-event announcement is a channel post, not a DM, and it is silently skipped when no announcement channel is configured.

---

## End Time, Completion and Staff

These work for every organization; none of them are locked features.

### End time

`Event.ends_at` is an optional end time for a single event, next to `scheduled_at` on
the create and edit forms (testid `event-end-datetime-input`). It must not be before the
start. Blank means a single-session event. It is separate from the series end date
(`EventRepeater.ends_at`, the create form's `ends_at` field), and events generated by a
series leave it blank.

When set, the Discord scheduled event the bot creates ends at `ends_at`; otherwise it
ends three hours after the start.

### Completing an event

Org owners and admins (`has_org_admin_access`) see **Complete** on an event in
`roll_call` or `in_progress`. It moves the event to `completed` through
`events.completion.close_event`, which:

1. moves the state with a conditional update, so a Complete press and the cleanup job
   racing on the same event close it once; the loser gets `closed: false`;
2. writes host and helper ledger entries and sets `contributions_awarded_at`;
3. invalidates the cached event after commit.

The event payload carries `user_can_manage_event_staff`, which gates the Complete button
and the staff editor. `state`, `host`, `helpers` and `contributions_awarded_at` are
read-only on `EventSerializer`: state changes go only through the action endpoints.

### Automatic close

The hourly `cleanup_stale_events` task closes events one day after they end
(`coalesce(ends_at, scheduled_at) + 1 day`, so a multi-day event is no longer closed a
day after it starts). It calls `POST /api/internal/events/{id}/auto-close/`:

| State | Becomes | Host/helper points |
|---|---|---|
| `roll_call`, `in_progress` | `completed` | awarded |
| `upcoming`, `signups_open` | `cancelled` | awarded if a host or helper is assigned |

The admin's manual **Cancel**, the generic internal `/transition/` endpoint and
`cleanup_stale_repeater_events` never award points.

### Host and helpers

Org owners and admins assign one host and any number of helpers from the event page.
Anyone can be assigned (their `OrgUser` is created if missing), and one person cannot
be both. The event payload carries their identity only (pk, name, avatar), never
points.

Once an event is `completed` or has `contributions_awarded_at` set, changing its host or
helpers updates the ledger immediately, and so does changing its name, `scheduled_at` or
`ends_at`. Points and the ledger are covered in
[Organization Locked Features](organization-locked-features.md#contributions).

---

## Roll Call

See [Roll Call](events/roll-call.md) for the dedicated roll call feature documentation.

---

## API Endpoints

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events/` | List events (filterable by org, state). `stale_before=<ISO 8601>` keeps events whose `coalesce(ends_at, scheduled_at)` is earlier; `400` if it doesn't parse. |
| POST | `/api/events/` | Create event (org staff only) |
| GET | `/api/events/{id}/` | Event detail |
| POST | `/api/events/{id}/signup/` | Canonical signup. Body: `{"intent": "rsvp" \| "tentative", "profile": {...SignupInputPatch}}`. Replaces the deleted `/rsvp/` and `/tentative/` actions. |
| POST | `/api/events/{id}/admin-signup/` | Staff signs another user up (e.g. via Discord interaction or manual add) |
| POST | `/api/events/{id}/open_signups/` | Transition to signups_open |
| POST | `/api/events/{id}/start_roll_call/` | Transition to roll_call |
| POST | `/api/events/{id}/start_tournament/` | Start tournament with the confirmed roster |
| POST | `/api/events/{id}/cancel/` | Cancel event. Deletes the linked tournament **and** the event's live Discord scheduled event, then clears `scheduled_event_id` so the 60-second `sync-discord-events` beat can't resurrect it. |
| POST | `/api/events/{id}/complete/` | Complete the event from `roll_call` or `in_progress` and award host/helper points (org admin). Returns the event; `400` from any other state or when another close won the race. |
| PUT | `/api/events/{id}/staff/` | Set host and helpers (org admin). Body: `{"host_id": <int\|null>, "helper_ids": [<int>, ...]}`. Returns the event. `400` if the host is also a helper or a user doesn't exist. Writes an `OrgLog` `set_event_staff` entry. |
| GET | `/api/events/{id}/discord-logs/` | Discord notification audit log for the event's tournament |
| GET | `/api/events/{id}/lobby-password/` | The event's lobby password. Org staff get `{mode, password, source, can_manage}`, registered players (approved or confirmed signup, or rostered) get `{password}`, anyone else `404`. Never cached. |
| POST | `/api/events/{id}/lobby-password/regenerate/` | New random lobby password (org staff); `409` in fixed mode. Existing lobbies keep theirs. |

### Signup actions (admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/event-signups/{id}/approve/` | Approve a signup. Optional body `{"mmr": <int>}` writes `OrgUser.mmr` and logs `set_mmr`. Does NOT mutate positions. |
| POST | `/api/event-signups/{id}/reject/` | Reject a signup |
| POST | `/api/event-signups/{id}/confirm/` | Confirm attendance (roll-call) |
| POST | `/api/event-signups/{id}/unconfirm/` | Reverse a confirm |
| POST | `/api/event-signups/{id}/demote/` | Demote approved/confirmed back to pending |
| POST | `/api/event-signups/{id}/cancel_signup/` | Cancel a signup (user or admin) |
| POST | `/api/event-signups/{id}/reinstate/` | Re-enable a cancelled signup |

### Repeaters & defaults

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events/repeaters/` | List repeaters |
| POST | `/api/events/repeaters/{id}/subscribe/` | Subscribe to repeater |
| POST | `/api/events/repeaters/{id}/unsubscribe/` | Unsubscribe |
| POST | `/api/events/repeaters/{id}/create-event/` | Create an extra ("one-off") event attached to the series (org staff). Body: `{"scheduled_at": <ISO8601>, "open_signups": <bool>, ...config overrides}`. Returns `201` with the event; `409` on an occurrence collision, `400` on a past/out-of-range time or an invalid override, `403` for non-staff. |
| GET | `/api/events/repeaters/{id}/lobby-password/` | The series' lobby password mode and fixed password (org staff; `404` for anyone else). |
| POST | `/api/events/repeaters/{id}/reactivate/` | Reactivate a paused series and realign its upcoming events (org staff). Returns `200` with `{"detail", "created_count", "is_active"}`. |
| GET | `/api/events/defaults/` | Get org event defaults |
| PATCH | `/api/events/defaults/{id}/` | Update org defaults |
| GET | `/api/discord/organizations/{id}/channels/` | List Discord channels |
