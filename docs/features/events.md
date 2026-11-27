# Event System

Schedule recurring events with Discord integration, automated signups, and tournament auto-creation.

## Overview

Organizations create one-off or recurring events that automatically generate tournaments. Players RSVP, admins approve/confirm attendance via roll call, and tournaments start with the confirmed roster.

- **Recurring event series** with configurable frequency (daily, weekly, bi-weekly, monthly)
- **Discord integration** — scheduled events, signup sync, channel announcements, attendance confirmation
- **Organization event defaults** — pre-fill event config from org-level settings
- **Repeater subscriptions** — subscribers get a Discord DM reminder to sign up before each series event
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
- **Player field** (shared): `steam_account_id`, the Steam Friend ID. It is stored once per player on `CustomUser.steam_account_id`, not on a game profile. A signup fills it when it is empty, accepts the same value again, and refuses a different value ("Your Friend ID is already set to X; contact an admin to change it"). Changing it is a profile or admin edit. A self-set ID must belong to a real Steam account and stays unverified until staff check it; see [Steam Friend ID verification](steam-friend-id.md).
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

Org admins configure default settings per organization in the **New Event Defaults** sections of the [organization settings modal](organization-settings.md#the-settings-modal), opened from the cog in the organization header. Org staff who are not admins cannot edit them. When creating new events, the form pre-fills from these defaults — no need to re-enter Discord channels, tournament config, or approval settings each time.

Ready check settings (Mandatory RSVP Confirmation, its timings and the start cull) can be saved as defaults too. The create form copies them, including `roll_call_enabled` and `roll_call_mode`, but never `auto_confirm`. See [Mandatory RSVP Confirmation](events/roll-call.md#mandatory-rsvp-confirmation).

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

### Deleting a Series

Deleting a series (`events.services.teardown_event_repeater`) also deletes its `upcoming`, `signups_open` and `roll_call` events, with their Discord scheduled events and tournaments. Its `in_progress`, `completed` and `cancelled` events are kept and lose their link to the series.

### Discord Integration

| Feature | Description |
|---------|-------------|
| Create scheduled event | Automatically creates a Discord scheduled event, only while the event's start time is in the future (Discord rejects past starts); once the start has passed, the Discord Tasks panel shows it as disabled and manual fire is refused |
| Synchronize signups | Keep website and Discord event signups in sync |
| Mark as interested | Players who sign up are marked interested on Discord |
| Signup channel | Post an embed to a channel for reaction-based signups |
| Pre-day announcement | Post a reminder in a channel before the event |
| Signup reminder | DM series subscribers who haven't signed up (recurring series only) |
| Profile reminder | Post a reminder in its own channel, or the announcement channel when none is picked, asking signed-up members to complete the profile details the event requires (such as Friend ID). With neither channel set, the Discord Tasks panel shows it as misconfigured |
| Attendance reminder | Post a reminder N hours before the event in its own channel, or the announcement channel when none is picked. With neither channel set, the Discord Tasks panel shows it as misconfigured. Replies aren't tracked; use the [ready check](events/roll-call.md) to require confirmation |
| New-event post | Series only (*Post new events*): post an embed when the series creates an event, in its own channel or the announcement channel when none is picked |
| Scheduled-event cleanup | Cancelling or deleting an event deletes its Discord scheduled event (`events.tasks.delete_discord_scheduled_event`), so nothing is left orphaned in the guild |

Each post that sends a channel message has its own channel field:

| Post | Channel field | When blank |
|---|---|---|
| Signup post | `discord_post_signups_channel_id` | Announcement channel while the pre-day announcement is on; otherwise not posted |
| Pre-day announcement | `discord_announcement_channel_id` | Not posted |
| Attendance reminder | `discord_confirm_attendance_channel_id` | Announcement channel |
| Profile reminder | `discord_profile_reminder_channel_id` | Announcement channel |
| New-event post | `discord_new_event_channel_id` | Announcement channel, whether or not the pre-day announcement is on |

The start mention has no channel: it replies to the signup post. Existing events and series have the three new fields blank, so they keep posting where they did before. An optional picker shows *Use announcement channel (#name)* while it is blank, has a clear button to go back to blank, and warns when neither it nor the announcement channel is set. The announcement channel picker sits in the pre-day announcement card while that post is on; otherwise it is shown at the end of the channel posts whenever a post with no channel of its own would fall back to it.

The Discord section of the event, series and organization defaults forms is split into three groups:

- **Server event**: the Discord scheduled event, its title and description, signup syncing and marking signups as interested.
- **Channel posts**: the signup post, start mention, pre-day announcement, attendance reminder, profile reminder and (series only) new-event post. Every post except the start mention has its own channel picker.
- **Direct messages**: the signup reminder DM to series subscribers. Single events show "Direct messages are set on recurring series." instead; in the organization defaults it is the default for new series.

Each message toggle has a **Preview** button that shows exactly what Discord will receive for the values in the form, without sending or saving anything. See [Discord Message Preview](events/discord-message-preview.md).

**Discord signup pipeline** (Dota events): clicking *Sign Up* either signs the user up directly (profile complete) or opens a modal with rank-status select → position select view → optional medal+star follow-up → optional screenshot upload. Each step routes through `events.services.apply_signup_input` — the **same service the web `/signup/` endpoint uses** — so the two paths converge on identical writes. Deadlock signups take a separate Discord-only branch that writes `PlayerDeadlockProfile.rank` directly.

### RSVP & Signups

Players RSVP from the event page (web) or via the Discord signup post. The signup flow respects event configuration:

- **Auto-approve** — signups go directly to Approved status
- **Manual approval** — admin reviews and approves each signup
- **Waitlist** — when max players is reached, new signups are waitlisted. A signup's waitlist position is its rank among the waitlisted signups in line order, and promotion takes the next waitlisted signup in line
- **Re-RSVP** — cancelled, declined and rejected signups can sign up again. The same signup is reused, so its history stays in one place
- **Main/Maybe switch** — switching between RSVP (Main) and tentative (Maybe) changes the same signup. Moving from Main to Maybe frees the seat for the next waitlisted signup

Each signup keeps a place in line and its original sign-up, and the signup ledger records every change to it, with who made it and how: see [Signup Ledger & Line Position](events/signup-ledger.md).

The **Signup Line** settings decide whether a returning or switching signup keeps its place in line. They sit on the event's approval tab, on the series' event tab and in the organization's New Event Defaults, and a series passes them on to its future events:

| Setting | Default | When on | When off |
|---|---|---|---|
| **Withdrawing gives up your place** (`line_withdraw_forfeits`) | on | A member who withdraws, declines or is rejected and signs up again goes to the back of the line | They get their old place back |
| **Switching Main/Maybe gives up your place** (`line_switch_restamps`) | on | Moving between Main and Maybe sends the signup to the back of the line | It keeps its place |

With both on, which is the default, the order is the same as before these settings existed. Signup rows on the event page and the roll call page show **in line since**: the time the signup took its current place.

#### Staff reasons

The **Staff reasons** setting (`staff_reason_policy`) decides when staff must say why they changed someone's signup. It sits next to the Signup Line settings, and a series passes it on to its future events like the other event settings. Past events keep the setting they had.

| Choice | Value | A reason is required for |
|---|---|---|
| **Optional** (default) | `optional` | nothing; staff can still give one |
| **Required for placements** | `placements` | placements only |
| **Required for every staff change** | `all_staff_changes` | every staff change to a signup |

Placements are the changes that decide who gets a seat: adding a member, approving a waitlisted signup, demoting to the waitlist and reinstating. Approving a pending signup, rejecting, confirming, unconfirming and removing are not placements.

No reason is ever needed for:

- a member changing their own signup, staff included;
- system changes such as waitlist promotions, series cascades and scheduled tasks;
- Discord buttons and commands, which are all member actions on the member's own signup. No staff Discord action exists. One added later would be refused under a strict policy until it collects a reason;
- event-level transitions: starting roll call, reopening signups, starting the tournament, cancelling, restarting and closing;
- ready check open, escalate and close. These apply the ready check rules to everyone at once, so no single member's change needs justifying. To remove one member with a reason, use Remove;
- voice presence and ready check resolve, which already require their own reason.

A reason that is given is saved with the change under every choice. Staff see it in the signup's **History**. Reasons are not shown to members, are not sent in live updates or Discord posts, and are not written to logs.

Under **Optional** the one-click buttons stay one-click. The actions that already open a dialog (the MMR approval recap, Remove, and the roll call confirm, reject and remove dialogs) get an optional reason field. When the choice requires a reason, a one-click action opens a short reason dialog first, and the dialog-based actions mark their field as required.

**API:** each staff signup action (`admin-signup`, `approve`, `demote`, `reinstate`, `reject`, `confirm`, `unconfirm`, `cancel_signup` and `ready-check/confirm`) accepts an optional `reason` in the body, at most 500 characters after trimming. When the event's choice requires one and none is sent, the endpoint returns 400 `{"error": "reason_required"}`. Status errors come first: a request on a signup in the wrong state gets the usual status error, not `reason_required`. `ready-check/recheck` writes no history, so it ignores `reason`.

#### Web vs Discord parity

Both signup paths funnel through `apply_signup_input` and write the same per-org `PlayerDotaProfile` row, so the two surfaces are interchangeable for Dota events. The table below shows where each field is captured and which model it lands on.

| Field | Web (`/signup/`) | Discord modal | Storage |
|---|---|---|---|
| `steam_account_id` (Friend ID) | ✓ when `require_steam_id` | ✓ modal text input, hidden once the player has one | `CustomUser.steam_account_id`, filled only when empty (Dota and Deadlock). The web form shows a stored ID read-only. |
| `positions` (Dota) | ✓ priority dict 0–5 per role (PositionForm) | ✓ slot-ordered list (1st / 2nd / 3rd choice selects) | `PlayerDotaProfile.pos_1..5` booleans (derived) **and** `CustomUser.positions` PositionsModel (priorities 1–5). Web sends a literal dict; Discord's `list[int]` is mapped to priorities by slot index (1st pick → priority 1, 2nd → 2, capped at 5; earliest slot wins on duplicate role). |
| `rank_status` (Dota) | ✓ RankStatusRadioGroup | ✓ rank select | `PlayerDotaProfile.rank_status` |
| `rank_medal` (Dota) | ✓ medal+star → joined ("Legend 4") | ✓ MedalSelect + StarSelect follow-up | `PlayerDotaProfile.rank_medal` |
| `battle_cup_tier` (Dota) | ✓ when `rank_status="never"` | ✓ BattleCupTierSelect | `PlayerDotaProfile.battle_cup_tier` |
| `rank_screenshot` (Dota) | ✓ URL field, validated for `.png/.jpg/.jpeg/.webp` | ✓ Discord attachment URL | `PlayerDotaProfile.rank_screenshot`. Required only when `rank_status="active"` and the event sets `discord_require_rank_screenshot`. "I had an MMR" (previous) records the rank via medal+star without a screenshot. |
| `battlecup_screenshot` (Dota) | ✓ | ✓ | `PlayerDotaProfile.battlecup_screenshot` |
| `deadlock_rank` | **not yet** | ✓ modal text | `PlayerDeadlockProfile.rank` |
| `mmr` numeric (admin-only) | ✓ on approve (`mmr_override`) | ✓ on approve | The org MMR of the **event's game** ([Org MMR per game](org-mmr.md)). `has_active_dota_mmr` and `dota_mmr_last_verified` are set only for Dota events. Also emits an `OrgLog` `set_mmr` entry with `game_type` |

The endpoint is a single canonical action accepting `{intent, profile}`; the older `/rsvp/` and `/tentative/` actions have been removed.

#### Approve flow

Admin approve uses `POST /api/event-signups/{id}/approve/` with optional `{ "mmr": <int> }`. On approve:

- `EventSignup.status` → `approved`.
- If `mmr` is supplied, the org MMR of the event's game is written and the OrgLog records `set_mmr` with `game_type`. The signup ledger's `approved` entry also records the override as `mmr_override` and `game_type` in its after snapshot. An `OrgUser` row is created if missing. The value is checked against that game's range (0–20000); an out-of-range value returns 400.
- The Dota verification flags (`has_active_dota_mmr`, `dota_mmr_last_verified`) are set only when the event is Dota 2.
- The approval dialog suggests a value only for Dota events (`suggested_mmr`). For Deadlock signups `suggested_mmr_range` is `null` with source `"none"`, and `suggested_mmr` is the member's existing Deadlock org MMR or `null`; the dialog shows the self-reported Deadlock rank instead and the input is required.
- **Approve does NOT mutate positions.** The legacy behavior that flattened `pos_N` booleans into `priority=1` on `CustomUser.positions` at approve time has been removed — priorities now come exclusively from the signup write via `apply_signup_input`, which is authoritative. The per-org `PlayerDotaProfile.pos_N` booleans are the derived binary view for that event.

### Repeater Subscriptions

Members subscribe to a series on the series page, from a series event's page, or with *Notify Me for Future Events* on a series event's signup post in Discord. None of these depend on *Post new events*; only the mail icon on the series cards in the organization's series list is shown just while *Post new events* is on. Two distinct notifications hang off a series, and they reach different audiences:

| When | What is sent | Gated by |
|---|---|---|
| An event is created from the series | A **channel embed** announcing the new event | `EventRepeater.discord_notify_new_events` (shown as *Post new events*); posted in `discord_new_event_channel_id`, or the announcement channel when blank; independent of the pre-day announcement toggle |
| `discord_signup_reminder_hours` before the event | A **DM to each series subscriber** who hasn't signed up yet | `discord_signup_reminder` (series only); sent only while signups are open and the event has a Discord scheduled event |

Subscribers without a linked Discord account get no DM, and a cancelled signup counts as not signed up.

Subscribing is what earns you the pre-event signup-reminder DM. The new-event announcement is a channel post, not a DM, and it is silently skipped when neither its own channel nor the announcement channel is set.

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
3. finalizes the event's attendance outcomes and sets `conduct_finalized_at` (see
   [Attendance outcomes](#attendance-outcomes));
4. invalidates the cached event after commit.

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

### Attendance outcomes

Events in an organization with [Conduct](organization-conduct.md) record an attendance
outcome for each expected member. The event lifecycle drives them:

| Action | Attendance outcomes |
|---|---|
| **Complete** or auto-close to `completed` | Finalized: members without an outcome become `attended` (default), except roll-call members who never confirmed, who stay pending for staff. Sets `conduct_finalized_at`. |
| **Cancel** or auto-close to `cancelled` | Voided, late cancels included. The event is read-only for conduct. Sets `conduct_finalized_at`. |
| **Reopen** | Clears `conduct_finalized_at`. Staff edits and late cancels are kept and unfinalized; default and automatic outcomes are deleted and worked out again at the next completion. The `reopen_event` log entry records `attendance_reopened`. |
| **Delete** | Unfinalized outcomes are deleted; finalized ones are voided and kept in member history as "Removed". |

Finalize and void each run once per event, inside the close's transaction, so a
Complete press racing the cleanup job does not double-process. They run whether or not
Conduct is unlocked; while it is locked they only finalize or void outcomes that already
exist. `conduct_finalized_at` is read-only on `EventSerializer`. The generic internal
`/transition/` endpoint and `cleanup_stale_repeater_events` skip these hooks.

A member's own cancel within the org's late-cancel window (or after the start) before
the event closes is recorded as a late cancel or no-show; staff actions never are.

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
| POST | `/api/events/{id}/cancel/` | Cancel event. Deletes the linked tournament **and** the event's live Discord scheduled event, then clears `scheduled_event_id` so the 60-second `sync-discord-events` beat can't resurrect it. Voids the event's attendance outcomes. |
| POST | `/api/events/{id}/complete/` | Complete the event from `roll_call` or `in_progress`, award host/helper points and finalize attendance outcomes (org admin). Returns the event; `400` from any other state or when another close won the race. |
| PUT | `/api/events/{id}/staff/` | Set host and helpers (org admin). Body: `{"host_id": <int\|null>, "helper_ids": [<int>, ...]}`. Returns the event. `400` if the host is also a helper or a user doesn't exist. Writes an `OrgLog` `set_event_staff` entry. |
| GET | `/api/events/{id}/discord-logs/` | Discord notification audit log for the event's tournament |
| GET | `/api/events/{id}/lobby-password/` | The event's lobby password. Org staff get `{mode, password, source, can_manage}`, registered players (approved or confirmed signup, or rostered) get `{password}`, anyone else `404`. Never cached. |
| POST | `/api/events/{id}/lobby-password/regenerate/` | New random lobby password (org staff); `409` in fixed mode. Existing lobbies keep theirs. |

### Signup actions (admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/event-signups/{id}/approve/` | Approve a signup. Optional body `{"mmr": <int>}` writes the org MMR of the event's game and logs `set_mmr`. Does NOT mutate positions. |
| POST | `/api/event-signups/{id}/reject/` | Reject a signup |
| POST | `/api/event-signups/{id}/confirm/` | Confirm attendance (roll-call) |
| POST | `/api/event-signups/{id}/unconfirm/` | Reverse a confirm |
| POST | `/api/event-signups/{id}/demote/` | Move an active signup to the waitlist; it moves to the back of the line. Nobody is promoted into the freed seat; staff fill it by hand |
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
