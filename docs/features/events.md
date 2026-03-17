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
| Signup reminder | DM users who haven't signed up |
| Profile reminder | DM users to complete their profile (Steam ID, MMR) |
| Confirm attendance | Require Discord reply to confirm attendance on event day |

### RSVP & Signups

Players RSVP from the event page. The signup flow respects event configuration:

- **Auto-approve** — signups go directly to Approved status
- **Manual approval** — admin reviews and approves each signup
- **Waitlist** — when max players is reached, new signups are waitlisted with position tracking
- **Re-RSVP** — cancelled signups can re-register

### Repeater Subscriptions

Users can subscribe to event repeaters (mail icon on repeater cards). When `discord_notify_new_events` is enabled, subscribed users are notified when new events are created or cancelled.

---

## Roll Call

See [Roll Call](events/roll-call.md) for the dedicated roll call feature documentation.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events/` | List events (filterable by org, state) |
| POST | `/api/events/` | Create event (org staff only) |
| GET | `/api/events/{id}/` | Event detail |
| POST | `/api/events/{id}/rsvp/` | RSVP for event |
| POST | `/api/events/{id}/open_signups/` | Transition to signups_open |
| POST | `/api/events/{id}/start_roll_call/` | Transition to roll_call |
| POST | `/api/events/{id}/start_tournament/` | Start tournament |
| POST | `/api/events/{id}/cancel/` | Cancel event |
| GET | `/api/events/repeaters/` | List repeaters |
| POST | `/api/events/repeaters/{id}/subscribe/` | Subscribe to repeater |
| POST | `/api/events/repeaters/{id}/unsubscribe/` | Unsubscribe |
| GET | `/api/events/defaults/` | Get org event defaults |
| PATCH | `/api/events/defaults/{id}/` | Update org defaults |
| GET | `/api/discord/organizations/{id}/channels/` | List Discord channels |
