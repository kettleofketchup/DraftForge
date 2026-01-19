# Captain's Mode Hero Draft Design

## Overview

Implement a real-time Captain's Mode hero draft system for tournament games. Two logged-in captains can draft heroes with reserve time mechanics, while spectators watch live.

## Entry Point

- Click bracket slot in tournament view → "View Draft" button
- Opens full-screen modal
- URL updates to `/tournament/{pk}/games/{game_pk}/draft`
- Back/ESC closes modal and restores previous URL

## Draft Sequence (24 Actions)

Updated Captain's Mode order (2024 patch):

| # | Action | Team | Phase |
|---|--------|------|-------|
| 1 | Ban | First | Ban Phase 1 |
| 2 | Ban | First | |
| 3 | Ban | Second | |
| 4 | Ban | Second | |
| 5 | Ban | First | |
| 6 | Ban | Second | |
| 7 | Ban | Second | |
| 8 | Pick | First | Pick Phase 1 |
| 9 | Pick | Second | |
| 10 | Ban | Second | Ban Phase 2 |
| 11 | Ban | First | |
| 12 | Ban | Second | |
| 13 | Pick | First | Pick Phase 2 |
| 14 | Pick | Second | |
| 15 | Pick | First | |
| 16 | Pick | Second | |
| 17 | Pick | First | |
| 18 | Pick | Second | |
| 19 | Ban | First | Ban Phase 3 |
| 20 | Ban | Second | |
| 21 | Ban | First | |
| 22 | Ban | Second | |
| 23 | Pick | First | Pick Phase 3 |
| 24 | Pick | Second | |

**Totals:** First team: 6 bans, 5 picks | Second team: 8 bans, 5 picks

## Timing

- **Reserve Time:** 90 seconds (1:30) per team total
- **Grace Time:** 30 seconds per action
- Grace time counts down first, then reserve time
- If reserve time hits 0 → auto-random pick from available heroes

## Roll Mechanism

1. Both captains must click "Ready"
2. Either captain can trigger the roll
3. Roll winner chooses EITHER:
   - Pick order (first pick or second pick)
   - Side (Radiant or Dire)
4. Other captain gets the remaining choice

## Data Models

### HeroDraft

Main draft instance.

| Field | Type | Description |
|-------|------|-------------|
| id | PK | Primary key |
| game | FK | TournamentGame |
| state | Enum | `waiting_for_captains`, `rolling`, `choosing`, `drafting`, `paused`, `completed` |
| roll_winner | FK | DraftTeam (nullable) |
| created_at | DateTime | |
| updated_at | DateTime | |

### DraftTeam

One per team in the draft.

| Field | Type | Description |
|-------|------|-------------|
| id | PK | Primary key |
| draft | FK | HeroDraft |
| tournament_team | FK | TournamentTeam |
| is_first_pick | Boolean | Nullable until chosen |
| is_radiant | Boolean | Nullable until chosen |
| reserve_time_remaining | Integer | Milliseconds, starts at 90000 |
| is_ready | Boolean | Ready-up phase |
| is_connected | Boolean | WebSocket status |

### HeroDraftRound

Each of the 24 actions.

| Field | Type | Description |
|-------|------|-------------|
| id | PK | Primary key |
| draft | FK | HeroDraft |
| draft_team | FK | DraftTeam (who acts) |
| round_number | Integer | 1-24 |
| action_type | Enum | `ban`, `pick` |
| hero_id | Integer | From dotaconstants, nullable |
| state | Enum | `planned`, `active`, `completed` |
| grace_time_ms | Integer | 30000 |
| started_at | DateTime | Nullable |
| completed_at | DateTime | Nullable |

### HeroDraftEvent

Audit log for disconnects, pauses, etc.

| Field | Type | Description |
|-------|------|-------------|
| id | PK | Primary key |
| draft | FK | HeroDraft |
| event_type | Enum | `captain_connected`, `captain_disconnected`, `draft_paused`, `draft_resumed`, `roll_triggered`, `choice_made` |
| draft_team | FK | DraftTeam (nullable) |
| metadata | JSON | Extra context |
| created_at | DateTime | |

## REST API Endpoints

### HeroDraft CRUD

```
POST   /api/games/{game_pk}/create-herodraft/
       → Creates HeroDraft with 24 pre-generated HeroDraftRounds
       → Returns full HeroDraft state

GET    /api/herodraft/{draft_pk}/
       → Returns full draft state including nested game, rounds, teams, timings
```

### HeroDraft Actions

```
POST   /api/herodraft/{draft_pk}/set-ready/
       → Mark captain as ready

POST   /api/herodraft/{draft_pk}/trigger-roll/
       → Trigger coin flip (requires both ready)

POST   /api/herodraft/{draft_pk}/submit-choice/
       → Roll winner chooses: { choice_type: "pick_order" | "side", value: "first" | "second" | "radiant" | "dire" }
       → After roll winner chooses, other captain chooses the remaining option

POST   /api/herodraft/{draft_pk}/submit-pick/
       → Submit hero_id for current round (picks and bans)
       → Validates: correct team, round is active, hero available
```

### Read-only

```
GET    /api/herodraft/{draft_pk}/list-events/
       → Audit log of all HeroDraftEvents

GET    /api/herodraft/{draft_pk}/list-available-heroes/
       → List of hero IDs not yet picked/banned
```

## WebSocket Events

Building on existing `draftevents` infrastructure.

### Server → Client (every second during active round)

```
draft_tick:
  - current_round: number
  - active_team_id: number
  - grace_time_remaining_ms: number
  - team_a_reserve_ms: number
  - team_b_reserve_ms: number
  - draft_state: string
```

### Server → Client (on state changes)

```
herodraft_updated:
  - Full serialized HeroDraft (game, draft_teams, rounds, state, timings)
  - Triggered on: ready, roll, choice, pick, pause, resume, timeout

captain_ready:           # a captain clicked ready
captain_connected:       # WebSocket connected
captain_disconnected:    # WebSocket disconnected, draft pauses
draft_paused:            # includes reason and timestamp
draft_resumed:           # draft continues
roll_result:             # who won the flip
choice_made:             # first pick or side selected
round_started:           # new round begins
hero_selected:           # pick/ban confirmed
round_timeout:           # auto-random pick triggered
draft_completed:         # all 24 rounds done
```

### Client → Server

```
captain_ready:           # captain clicks ready button
trigger_roll:            # captain initiates coin flip
select_first_pick:       # roll winner chooses first/second pick
select_side:             # captain chooses radiant/dire
select_hero:             # captain picks/bans a hero
confirm_selection:       # "are you sure" confirmation for bans
```

### Connection Handling

- On disconnect: Pause draft, record `HeroDraftEvent`, broadcast `draft_paused`
- On reconnect: Resume draft, record event, broadcast `draft_resumed`
- Timeout after 5 minutes of disconnect → draft abandoned (configurable)

## UI Components

### Top Bar (2 rows, 5 columns)

```
┌─────────────────┬─────────────────┬───────────┬─────────────────┬─────────────────┐
│ Captain A       │ Captain A       │           │ Captain B       │ Captain B       │
│ (avatar+name)   │ Picks/Bans      │   VS      │ Picks/Bans      │ (avatar+name)   │
├─────────────────┼─────────────────┼───────────┼─────────────────┼─────────────────┤
│ Reserve: 1:30   │                 │ Pick: 0:30│                 │ Reserve: 1:30   │
│ (ticks down)    │                 │ (active)  │                 │ (ticks down)    │
└─────────────────┴─────────────────┴───────────┴─────────────────┴─────────────────┘
```

- Use existing CaptainPopover component for captain display
- Active team highlighted
- Reserve time ticks down after grace time expires
- Current pick timer shows grace time countdown

### Pre-Draft Phases

- **Waiting:** "Ready" buttons for each captain
- **Rolling:** Coin flip animation, shows winner
- **Choosing:** Roll winner picks (first pick OR side), then other captain picks remaining

### Left Column - Hero Grid

```
┌─────────────────────────────────────┐
│ 🔍 Search heroes...                 │
├─────────────────────────────────────┤
│ STRENGTH                            │
│ [hero][hero][hero][hero][hero]...   │
├─────────────────────────────────────┤
│ AGILITY                             │
│ [hero][hero][hero][hero][hero]...   │
├─────────────────────────────────────┤
│ INTELLIGENCE                        │
│ [hero][hero][hero][hero][hero]...   │
├─────────────────────────────────────┤
│ UNIVERSAL                           │
│ [hero][hero][hero][hero][hero]...   │
└─────────────────────────────────────┘
```

- Hero icons from dotaconstants
- Search filters with grayscale on non-matches
- Picked/banned heroes grayed out with overlay
- Hover shows hero name tooltip
- Click hero → confirmation dialog ("Ban [Hero]?" / "Pick [Hero]?")
- Only active captain sees action buttons (spectators can browse but no buttons)

### Right Column - Draft Panel (Dota-style)

```
┌────────────────────────────────────────────────┐
│     RADIANT              │           DIRE      │
│     (green glow)         │       (red glow)    │
├────────────────────────────────────────────────┤
│                          │                     │
│  [ban slot] ─────── 1    │                     │
│  [ban slot] ─────── 2    │                     │
│                     3 ───────── [ban slot]     │
│                     4 ───────── [ban slot]     │
│  [ban slot] ─────── 5    │                     │
│                     6 ───────── [ban slot]     │
│                     7 ───────── [ban slot]     │
│                          │                     │
│  [PICK SLOT] ────── 8    │                     │
│                     9 ───────── [PICK SLOT]    │
│                          │                     │
│  ... continues to 24 ... │                     │
│                          │                     │
└────────────────────────────────────────────────┘
```

- Dark translucent background
- RADIANT header with green accent/glow
- DIRE header with red accent/glow
- Dark rounded slots with beveled edges
- Pick order numbers (1-24) centered between columns
- Thin connector lines from number to active team's slot
- Ban slots: smaller
- Pick slots: larger
- Active slot has subtle glow/pulse
- Completed slots show hero portrait

### Bottom Row - Team Chat (Placeholder)

```
┌────────────────────────────────────────────────┐
│  💬 Team Chat                                  │
│  ┌──────────────────────────────────────────┐  │
│  │     🚧 Under Construction 🚧              │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

- Placeholder for future team-to-team chat
- TODO for later implementation

## Draft State Flow

```
┌──────────────────┐
│ waiting_for_     │  Both captains connect via WebSocket
│ captains         │
└────────┬─────────┘
         │ Both click "Ready"
         ▼
┌──────────────────┐
│ rolling          │  Either captain triggers roll
└────────┬─────────┘
         │ Coin flip result
         ▼
┌──────────────────┐
│ choosing         │  Winner picks (side OR pick order)
│                  │  Then other captain picks remaining
└────────┬─────────┘
         │ Both choices made
         ▼
┌──────────────────┐         ┌──────────────────┐
│ drafting         │◄───────►│ paused           │
│                  │ disconnect/reconnect
└────────┬─────────┘         └──────────────────┘
         │ All 24 rounds complete
         ▼
┌──────────────────┐
│ completed        │  Final state, draft locked
└──────────────────┘
```

## Spectator Mode

- Anonymous WebSocket connections allowed
- Receive all broadcast events (read-only)
- Can browse/search hero grid, hover for names
- No pick/ban action buttons shown
- View-only draft panel and timers

## Technical Stack

**Backend:**
- 4 new models: `HeroDraft`, `DraftTeam`, `HeroDraftRound`, `HeroDraftEvent`
- 6 API endpoints under `/api/herodraft/` and `/api/games/`
- WebSocket consumer extending existing `draftevents` infrastructure
- Background task for tick broadcasts (every second during active round)

**Frontend:**
- `HeroDraftModal` - full-screen modal with URL sync
- `DraftTopBar` - captain info, timers, reserve time
- `HeroGrid` - searchable grid by attribute, click to pick/ban
- `DraftPanel` - Dota-style vertical columns with connector lines
- `DraftChatPlaceholder` - under construction message
- WebSocket hook for real-time updates

**Hero Data:**
- Source from `dotaconstants` npm package
- ~124 heroes, grouped by primary attribute (Strength, Agility, Intelligence, Universal)

## Out of Scope (Future)

- Team chat functionality
- Draft replays
- Custom draft formats
