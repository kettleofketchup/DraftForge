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

### Organization Event Defaults

Admins configure default settings per organization. When creating new events, the form pre-fills from these defaults — no need to re-enter Discord channels, tournament config, or approval settings each time.

### Discord Integration

| Feature | Description |
|---------|-------------|
| Create scheduled event | Automatically creates a Discord scheduled event |
| Synchronize signups | Keep website and Discord event signups in sync |
| Mark as interested | Players who sign up are marked interested on Discord |
| Signup channel | Post an embed to a channel for reaction-based signups |
| Pre-day announcement | Post a reminder in a channel before the event |
| Signup reminder | DM subscribers who haven't signed up (recurring series only) |
| Profile reminder | DM users to complete their profile (Steam ID, MMR) |
| Confirm attendance | Require Discord reply to confirm attendance on event day |

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

Users can subscribe to event repeaters (mail icon on repeater cards). When `discord_notify_new_events` is enabled, subscribed users are notified when new events are created or cancelled.

---

## Roll Call

See [Roll Call](events/roll-call.md) for the dedicated roll call feature documentation.

---

## API Endpoints

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events/` | List events (filterable by org, state) |
| POST | `/api/events/` | Create event (org staff only) |
| GET | `/api/events/{id}/` | Event detail |
| POST | `/api/events/{id}/signup/` | Canonical signup. Body: `{"intent": "rsvp" \| "tentative", "profile": {...SignupInputPatch}}`. Replaces the deleted `/rsvp/` and `/tentative/` actions. |
| POST | `/api/events/{id}/admin-signup/` | Staff signs another user up (e.g. via Discord interaction or manual add) |
| POST | `/api/events/{id}/open_signups/` | Transition to signups_open |
| POST | `/api/events/{id}/start_roll_call/` | Transition to roll_call |
| POST | `/api/events/{id}/start_tournament/` | Start tournament with the confirmed roster |
| POST | `/api/events/{id}/cancel/` | Cancel event |
| GET | `/api/events/{id}/discord-logs/` | Discord notification audit log for the event's tournament |

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
| GET | `/api/events/defaults/` | Get org event defaults |
| PATCH | `/api/events/defaults/{id}/` | Update org defaults |
| GET | `/api/discord/organizations/{id}/channels/` | List Discord channels |
