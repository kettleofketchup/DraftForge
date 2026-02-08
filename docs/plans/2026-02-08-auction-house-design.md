# Auction House Design Plan

**Date:** 2026-02-08
**Status:** Design Complete

## Overview

The Auction House is an alternative team formation method alongside snake/normal/shuffle drafts. Captains take turns nominating a player from the pool, then all captains bid using a virtual salary cap budget. The highest bidder wins the player at their bid price. When a team's budget runs out, remaining roster slots are filled via shuffle draft fallback (configurable).

Works at both tournament and season level.

---

## AuctionConfig (Cascading)

Configuration inherits down the hierarchy: Organization → League → Season → Tournament. Each level stores only fields it explicitly overrides (JSONField). Null fields mean "inherit from parent." A `get_resolved_auction_config()` helper merges all layers against system defaults.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `budget` | int | 1000 | Starting salary cap per team |
| `min_bid` | int | 1 | Minimum opening bid / increment |
| `bid_timer` | int | 15 | Initial seconds for bidding window after nomination |
| `bid_extension_timer` | int | 5 | Timer resets to this if bid lands in final N seconds |
| `nomination_timer` | int | 30 | Seconds to nominate before auto-pick |
| `unsold_behavior` | enum | `auto_assign` | `auto_assign` (nominator gets at min_bid) or `return_to_pool` |
| `max_roster_size` | int | 5 | Team size (captain + picked members) |
| `fallback_mode` | enum | `shuffle` | `shuffle` (lowest MMR picks first) or `skip` (team can't acquire more) |
| `max_pauses_per_captain` | int/null | null | Max disconnect pauses per captain (null = unlimited) |
| `reconnect_timeout` | int | 120 | Seconds to wait for captain reconnect before continuing without them |

**Resolution example:** Org sets `budget: 2000`, `bid_timer: 20`. League sets `min_bid: 5`. Tournament sets `max_roster_size: 6`. Resolved for that tournament: budget=2000, min_bid=5, bid_timer=20, bid_extension_timer=5, nomination_timer=30, unsold_behavior=auto_assign, max_roster_size=6, fallback_mode=shuffle, max_pauses_per_captain=null, reconnect_timeout=120.

---

## Data Model

### Auction

| Field | Type | Description |
|-------|------|-------------|
| `tournament` | FK (nullable) | Tournament link |
| `season` | FK (nullable) | Season link (alternative scope) |
| `status` | enum | `pending` / `nominating` / `bidding` / `paused` / `fallback_drafting` / `completed` |
| `nomination_order` | JSONField | Ordered list of team IDs for rotation |
| `current_nominator_index` | int | Position in rotation |
| `created_at` | datetime | |
| `updated_at` | datetime | |

Constraint: Exactly one of `tournament` or `season` must be set (not both, not neither).

### AuctionTeamBudget

| Field | Type | Description |
|-------|------|-------------|
| `auction` | FK | Parent auction |
| `team` | FK | Team |
| `budget_remaining` | int | Current budget |
| `players_won` | int | Count of players won via bidding |
| `pause_count` | int | Disconnect pauses used by this captain |

Constraint: unique_together (auction, team).

### AuctionLot

| Field | Type | Description |
|-------|------|-------------|
| `auction` | FK | Parent auction |
| `player` | FK (User) | Nominated player |
| `nominator` | FK (Team) | Who nominated |
| `lot_number` | int | Sequence order |
| `status` | enum | `bidding` / `sold` / `unsold` |
| `winning_team` | FK (nullable) | Who won |
| `winning_bid` | int (nullable) | Final price |
| `started_at` | datetime | When bidding opened |
| `ended_at` | datetime (nullable) | When lot closed |

### AuctionBid

| Field | Type | Description |
|-------|------|-------------|
| `lot` | FK | Parent lot |
| `team` | FK | Bidding team |
| `amount` | int | Bid amount |
| `created_at` | datetime | |

---

## Auction Flow & State Machine

```
pending → nominating → bidding → (repeat) → fallback_drafting → completed
```

1. **Admin creates auction** — links to tournament or season, config resolved from hierarchy. Teams and player pool locked in.

2. **Nomination phase** (`nominating`) — Current captain in rotation has `nomination_timer` seconds to nominate any player from the pool. Timer expires → auto-nominate highest-MMR remaining player. Nomination sets opening bid at `min_bid` with nominator as initial bidder.

3. **Bidding phase** (`bidding`) — All captains with budget and roster space can bid. Each bid must be >= current highest + `min_bid`. Each bid resets countdown IF remaining time <= `bid_extension_timer` (resets to `bid_extension_timer`). Timer expires with no new bids → lot closes:
   - Player assigned to winning team's roster
   - Winning bid deducted from team budget
   - Team full → removed from rotation
   - If no bids besides nominator → `unsold_behavior` applies

4. **Back to nomination** — Rotation advances to next eligible captain (has budget >= `min_bid` AND has roster slots). No eligible captains but teams still have empty slots → transition to fallback.

5. **Fallback drafting** (`fallback_drafting`) — Teams with remaining roster slots but no budget pick from remaining pool using shuffle logic (lowest team MMR picks first, ties broken by 1d6 roll-off). Each pick at cost 0. Continues until all teams full or pool exhausted.

6. **Completed** — All teams full or pool exhausted.

### Bid Timer Behavior

Example: Lot opens → 15s countdown. At 8s remaining, bid comes in → no reset (8 > 5). At 3s remaining, another bid → timer resets to 5s. At 2s of new window, another bid → resets to 5s again. No bid for 5s → lot closes.

### Captain Disconnect / Pause

Reuses HeroDraft's heartbeat/connected tracking pattern:
- Captain disconnects → auction auto-pauses, waits up to `reconnect_timeout` seconds
- Captain reconnects → auction resumes, `pause_count` incremented on their AuctionTeamBudget
- Captain exceeds `max_pauses_per_captain` (if set) and disconnects again → auction continues without them (nomination turns skipped, can't bid until reconnect)
- Admin manual pauses are separate and don't count against captain pause budgets

---

## API Endpoints

### REST

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/tournaments/{id}/create-auction/` | Create auction for tournament | Org Staff |
| POST | `/api/seasons/{id}/create-auction/` | Create auction for season | League Admin |
| GET | `/api/auctions/{id}/` | Get auction state | No |
| POST | `/api/auctions/{id}/pause/` | Admin pause | Org Staff |
| POST | `/api/auctions/{id}/resume/` | Admin resume | Org Staff |
| POST | `/api/auctions/{id}/abort/` | Abort auction | Org Staff |
| GET | `/api/auctions/{id}/results/` | Final results | No |

### AuctionConfig (per-entity)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/organizations/{id}/auction-config/` | Get org config | No |
| PUT | `/api/organizations/{id}/auction-config/` | Set org config | Org Admin |
| GET | `/api/leagues/{id}/auction-config/` | Get league config | No |
| PUT | `/api/leagues/{id}/auction-config/` | Set league config | League Admin |
| GET | `/api/seasons/{id}/auction-config/` | Get season config | No |
| PUT | `/api/seasons/{id}/auction-config/` | Set season config | League Admin |
| GET | `/api/tournaments/{id}/auction-config/` | Get tournament config | No |
| PUT | `/api/tournaments/{id}/auction-config/` | Set tournament config | Org Staff |
| GET | `/api/tournaments/{id}/auction-config/resolved/` | Get merged config | No |

### WebSocket

`/api/auction/{auction_id}/` — Daphne protocol routing, same pattern as HeroDraft.

**Client messages:**

| Message | Payload | Description |
|---------|---------|-------------|
| `start` | — | Admin triggers auction start |
| `nominate` | `{ player_id }` | Captain nominates a player |
| `bid` | `{ amount }` | Place bid on current lot |

**Server broadcast events:**

| Event | Payload |
|-------|---------|
| `auction_started` | Auction state, budgets, pool |
| `nomination` | Lot details, nominator, player, opening bid |
| `bid_placed` | Lot ID, team, amount, time remaining |
| `lot_sold` | Lot ID, winning team, price, updated budgets |
| `lot_unsold` | Lot ID, auto-assigned to nominator |
| `fallback_pick` | Team, player, team MMR |
| `captain_disconnected` | Team ID, pause_count |
| `captain_reconnected` | Team ID |
| `auction_paused` / `auction_resumed` | Timestamp, reason |
| `auction_completed` | Final results summary |

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Captain disconnects during nomination | Auto-pause, wait for reconnect. If `reconnect_timeout` expires or pauses exhausted, skip their turn and continue. |
| Captain disconnects during bidding | Auto-pause, wait. Other captains' bids are preserved. |
| All captains disconnect | Auction pauses. Resumes when any captain reconnects. |
| Bid exceeds team's remaining budget | Rejected server-side. Client disables bids above budget. |
| Budget can't cover remaining roster at min_bid | Must reserve `min_bid * remaining_slots` — bid capped at `budget - (min_bid * (slots_needed - 1))`. |
| Two bids at identical timestamp | First processed by server wins (serial WebSocket). |
| Nominator is only bidder | Wins at min_bid (auto_assign behavior). |
| Team full mid-auction | Removed from rotation, can't nominate or bid. |
| Captain exhausts pause budget, disconnects again | Auction continues without them. Turns skipped, can't bid. Reconnect restores bidding ability. |
| Admin aborts mid-auction | Players already assigned stay. Remaining pool unassigned. |
| Concurrent auctions | Not supported — one active per tournament/season. |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSONField for cascading config | Simple merge, no extra joins, nullable = inherit |
| Nomination rotation | Adds strategy, prevents chaotic simultaneous bidding |
| Auto-nominate on timeout | Keeps auction moving, prevents stalling |
| Bid extension timer | Prevents sniping while keeping pace fast |
| Budget reserve check | Ensures teams can always fill roster at minimum |
| Shuffle fallback for broke teams | Reuses existing code, natural MMR-based balancing |
| Heartbeat-based pause on disconnect | Reuses HeroDraft pattern, configurable pause limits |
| WebSocket same as HeroDraft | Consistent architecture across all real-time features |
