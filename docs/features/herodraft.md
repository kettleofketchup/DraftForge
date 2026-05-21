# Hero Draft (Captain's Mode)

The Hero Draft system implements Dota 2's Captain's Mode for tournament matches, allowing team captains to ban and pick heroes in real-time via WebSocket.

| Captain 1 Perspective | Captain 2 Perspective |
|-----------------------|-----------------------|
| ![Captain 1](https://assets.kettle.sh/draftforge/gifs/captain1_herodraft.gif) | ![Captain 2](https://assets.kettle.sh/draftforge/gifs/captain2_herodraft.gif) |
| [:material-play-circle: Full Video](https://assets.kettle.sh/draftforge/videos/captain1_herodraft.webm) | [:material-play-circle: Full Video](https://assets.kettle.sh/draftforge/videos/captain2_herodraft.webm) |

## Overview

Hero Draft runs through several phases:

1. **Waiting** - Captains connect and ready up
2. **Rolling** - Coin flip to determine who chooses first
3. **Choosing** - Winner picks first pick OR side, loser gets remaining choice
4. **Drafting** - 24 rounds of bans and picks with timers
5. **Completed** - Draft finished, results saved

## Data Models

### HeroDraft

| Field | Type | Description |
|-------|------|-------------|
| `game` | OneToOneField | Associated tournament game |
| `state` | CharField | Current phase (see HeroDraftState) |
| `roll_winner` | ForeignKey | Team that won the coin flip |
| `paused_at` | DateTimeField | Timestamp when draft was paused (null if not paused) |
| `created_at` | DateTimeField | Creation timestamp |
| `updated_at` | DateTimeField | Last update timestamp |

### HeroDraftState

| State | Description |
|-------|-------------|
| `waiting_for_captains` | Waiting for both captains to connect and ready |
| `rolling` | Coin flip phase |
| `choosing` | Winner/loser making pick order and side choices |
| `drafting` | Active ban/pick phase with timers |
| `paused` | Draft paused (captain disconnect or manual via captain/staff). Server stops broadcasting ticks. |
| `resuming` | 3-second countdown between PAUSED → DRAFTING. `resuming_until` carries the target timestamp. |
| `completed` | Draft finished successfully |
| `abandoned` | Draft cancelled |

### DraftTeam

| Field | Type | Description |
|-------|------|-------------|
| `draft` | ForeignKey | Parent HeroDraft |
| `tournament_team` | ForeignKey | Associated tournament team |
| `is_first_pick` | Boolean | Whether team has first pick |
| `is_radiant` | Boolean | Whether team is Radiant side |
| `reserve_time_remaining` | Integer | Reserve time in milliseconds (default 90000) |
| `is_ready` | Boolean | Whether captain has readied up |
| `is_connected` | Boolean | Whether captain is currently connected |

### HeroDraftRound

| Field | Type | Description |
|-------|------|-------------|
| `draft` | ForeignKey | Parent HeroDraft |
| `draft_team` | ForeignKey | Team making this pick/ban |
| `round_number` | Integer | Sequential round number (1-24) |
| `action_type` | CharField | `ban` or `pick` |
| `hero_id` | Integer | Selected hero ID (null until chosen) |
| `state` | CharField | `planned`, `active`, or `completed` |
| `grace_time_ms` | Integer | Grace time for this round (default 30000) |
| `started_at` | DateTimeField | When round became active |
| `completed_at` | DateTimeField | When round was completed |

## WebSocket Architecture

### Connection

Clients connect via WebSocket to `/api/herodraft/<draft_id>/`. The `HeroDraftConsumer` handles:

- Connection tracking (captain vs spectator)
- Initial state delivery
- Event broadcasting
- Pause/resume logic

### Events (Server → Client)

| Event Type | Description | Payload |
|------------|-------------|---------|
| `initial_state` | Full draft state on connect | `{draft_state: {...}}` |
| `captain_connected` | Captain joined | `{draft_team: {...}}` |
| `captain_disconnected` | Captain left | `{draft_team: {...}}` |
| `captain_ready` | Captain readied up | `{draft_team: {...}}` |
| `draft_paused` | Draft paused (captain disconnect) | `{metadata: {reason: "captain_disconnected"}}` |
| `resume_countdown` | Countdown before resume | `{metadata: {countdown_seconds: 3}}` |
| `draft_resumed` | Draft resumed | `{}` |
| `roll_triggered` | Coin flip started | `{}` |
| `roll_result` | Coin flip result | `{draft_team: {...}}` |
| `choice_made` | Pick order/side chosen | `{draft_team: {...}}` |
| `round_started` | New round began | `{draft_state: {...}}` |
| `hero_selected` | Hero picked/banned | `{draft_state: {...}}` |
| `draft_completed` | Draft finished | `{draft_state: {...}}` |

### Tick Updates

During `drafting` and `resuming` phases, the server broadcasts `herodraft_tick` at 1Hz. Ticks carry **anchors** (server timestamps + durations), not pre-computed remainders — the client derives the countdown locally via `requestAnimationFrame` so the displayed timer stays smooth even when ticks are delayed, batched, or dropped.

**DRAFTING tick:**

```json
{
  "type": "herodraft_tick",
  "draft_state": "drafting",
  "server_time": "2026-05-21T18:42:13.421Z",
  "current_round": 0,
  "active_team_id": 123,
  "round_started_at": "2026-05-21T18:42:08.000Z",
  "round_grace_time_ms": 30000,
  "team_a_id": 123,
  "team_a_reserve_ms": 90000,
  "team_b_id": 456,
  "team_b_reserve_ms": 85000
}
```

**RESUMING tick** (during the 3s countdown after pause):

```json
{
  "type": "herodraft_tick",
  "draft_state": "resuming",
  "server_time": "2026-05-21T18:43:11.005Z",
  "resuming_until": "2026-05-21T18:43:14.000Z"
}
```

`team_a_reserve_ms` / `team_b_reserve_ms` are the team's **cumulative reserve at round start** (stable for the duration of the round). The active team's display value is computed client-side as `max(0, reserve - max(0, elapsed - grace))`. The server debits actual usage at pick-submit time, so the *next* round's tick carries the lower value forward.

### Client-Side Countdown

The store captures `serverClockOffsetMs = server_time - Date.now()` once on every tick receive. `useDraftCountdown` runs a `requestAnimationFrame` loop and recomputes the display values each frame against `Date.now() + serverClockOffsetMs` and the current tick's anchors. This decouples timer smoothness from broadcast cadence — even a 5-second tick gap doesn't freeze the UI.

**While paused, the server stops broadcasting ticks**, so the cached tick keeps reading `drafting` with a stale `round_started_at`. The hook reads the live `draft.state` from the store and skips its `setState` call while paused, freezing the displayed values until the next tick arrives (during RESUMING).

**Outbound timestamps** use `getServerNowISO()` (also derived from the offset). `submitPick` sends `client_picked_at` so the server can credit reserve against the picker's local clock rather than the server-receive time. The server applies a 2-second sanity window: stamps older than 2s or in the future fall back to server-receive.

## Pause/Resume System

### Trigger Conditions

The draft **pauses immediately** when:
- Any captain's heartbeat goes stale (>9s without keepalive) during `drafting`
- A captain or tournament staff member POSTs to `/api/herodraft/<pk>/pause/` (manual pause; sets `is_manual_pause=true`)

The draft **resumes** when:
- POST to `/api/herodraft/<pk>/resume/` by a captain or tournament staff
- Server transitions PAUSED → RESUMING with a 3-second countdown anchor (`resuming_until`)
- After 3s the tick loop transitions RESUMING → DRAFTING

### Backend Logic

**On Pause (heartbeat-stale or manual):**

1. Set `draft.state = PAUSED`
2. Store `draft.paused_at = now()`
3. Broadcast `draft_paused` event to all clients
4. Tick broadcaster stops on next iteration (`should_continue_ticking` returns False)

**On Resume (manual):**

1. Calculate `pause_duration = now() - draft.paused_at`
2. Adjust active round's `started_at` forward by `pause_duration + 3 seconds` and `save(update_fields=["started_at"])`
3. Set `draft.state = RESUMING`, `resuming_until = now() + 3s`, clear `paused_at` and `is_manual_pause`
4. Restart tick broadcaster — first ticks carry the RESUMING anchor; clients display "Resuming in N…"
5. After `resuming_until` passes, the tick loop's `check_resume_countdown` flips the draft to `DRAFTING` and broadcasts `draft_resumed`. Subsequent ticks carry the new `round_started_at`

**Timer Adjustment:**

The key insight is that elapsed time is calculated as:
```python
elapsed_ms = (now - round.started_at).total_seconds() * 1000
```

By pushing `started_at` forward by the pause duration + countdown, the elapsed time calculation automatically excludes the pause period.

### Edge Case: Disconnect During Countdown

If a captain disconnects during the "Resuming in 3...2...1..." countdown:
- Backend is already in DRAFTING state
- Disconnect triggers pause logic again
- Frontend receives `draft_paused`, cancels countdown, shows pause overlay

### Timing Tolerances

For responsive UX:
- Pause overlay should appear within 100ms of disconnect
- Resume countdown should start within 100ms of all captains connected
- Timer should resume exactly where it paused (no drift)

## Observability

Telemetry plumbing is shared across the whole backend (see [dev/telemetry/](../dev/telemetry/index.md)). This section documents what herodraft-specific signals you can expect and how to query them.

### Spans (Tempo)

| Span | Emitted by | Useful attributes |
|------|-----------|-------------------|
| `ws.connect`, `ws.disconnect`, `ws.heartbeat`, `ws.message` | `consumers_base.py` | `ws.draft_id`, `ws.user_id`, `ws.conn_id` |
| `ws.captain_register`, `ws.captain_unregister` | `consumers.py` | `ws.draft_id`, `ws.user_id`, `ws.draft_team_id` |
| `herodraft.submit_pick` | `functions/herodraft.py` | `draft.id`, `team.id`, `hero.id`, `round.number`, `elapsed_ms`, `over_grace_ms`, `reserve_used_ms`, `pick_time_source` (`client_now`, `server_now`, fallback reason) |
| `herodraft.tick.iteration` | `tasks/herodraft_tick.py` | `ws.draft_id`, `tick.iteration`, `tick.duration_s`, `tick.outcome`, `tick.stop_reason` |
| `herodraft.tick.<step>` | `tasks/herodraft_tick.py` | child of `tick.iteration`. Steps: `resume_countdown`, `captain_heartbeats`, `broadcast_tick`, `check_timeout`, `extend_lock`. Each carries `tick.step_duration_s` |

`herodraft.submit_pick` runs inside the parent `ws.message` span, so a single trace shows: client message arrives → handler dispatches → pick logic → DB commit → broadcast. Look for the trace by `ws.draft_id` or via the `traceID` derived field on any associated log line.

**Sample TraceQL (Tempo Explore):**

```traceql
# Every pick in a draft
{ name = "herodraft.submit_pick" && .draft.id = 123 }

# Slow tick iterations
{ name = "herodraft.tick.iteration" && duration > 1500ms }

# Picks where the server fell back from client_picked_at
{ name = "herodraft.submit_pick" && .pick_time_source != "client_now" }
```

### Log events (Loki)

All logs carry `system="herodraft"` plus a `subsystem` discriminator. Filter by `service_name="backend"` for the relevant stream.

| `subsystem` | Event | Level | Trigger |
|-------------|-------|-------|---------|
| `state` | `draft_paused` | info | Manual pause (captain/staff POST to `/pause/`) |
| `state` | `draft_resumed` | info | Manual resume; includes `pause_duration_s`, `round_started_at_adjustment_s` |
| `timing` | `round_started_at_adjusted` | info | Round anchor pushed forward by pause duration + 3s countdown |
| `heartbeat` | `heartbeat_missing` | warning | No heartbeat key in Redis for a connected captain |
| `heartbeat` | `heartbeat_stale` | warning | Heartbeat older than 9s |
| `heartbeat` | `heartbeat_triggered_pause` | info | Heartbeat-stale forced a state → PAUSED transition |
| `timer` | `tick_loop_started` / `tick_loop_stopping` / `tick_loop_ended` | info | Broadcaster lifecycle. `tick_loop_stopping.reason` is `no_connections`, `draft_state_paused`, `draft_state_completed`, etc. |
| `timer` | `tick_loop_healthy` | info | Heartbeat log every 30 ticks with `duration_s` |
| `timer` | `tick_loop_stalled` | error | Gap between consecutive ticks >1.5s (event loop blocked) |
| `timer` | `tick_skipped` | info / warning | `reason` ∈ {`wrong_state`, `no_active_round`, `not_found`} |
| `timer` | `tick_step_slow` / `tick_slow` | warning | Sub-step >300ms or whole iteration >1.5s |
| `timer` | `timeout_auto_pick` / `timeout_auto_pick_broadcast` | info | Auto-random fired (over grace + reserve) |
| `pick` | `pick_submitted` | info | Includes `elapsed_ms`, `over_grace_ms`, `reserve_used_ms`, `pick_time_source` |
| `pick` | `pick_time_too_old` / `pick_time_in_future` / `pick_time_naive_datetime` | warning | Server rejected `client_picked_at` and fell back to receive-time |
| `pick` | `pick_reserve_exhausted` | warning | Active team finished pick with reserve_time_remaining ≤ 0 |
| `pick` | `pick_elapsed_negative` | error | `now - round_started_at` < 0 (clock skew or DB clock drift) |

**Sample LogQL queries:**

```logql
# Full lifecycle of a specific draft
{service_name="backend"} | json | draft_id="123"

# Every pause/resume event across the cluster, with timing
{service_name="backend"} | json | event_name=~"draft_paused|draft_resumed|round_started_at_adjusted"

# Tick health for a draft (cadence, slow steps, stalls)
{service_name="backend"} | json | system="herodraft" | subsystem="timer" | draft_id="123"

# Captains whose heartbeat went stale (potential disconnect leading to pause)
{service_name="backend"} | json | event_name=~"heartbeat_(stale|missing|triggered_pause)"

# Picks that crossed grace and burned reserve, sorted by burn amount
{service_name="backend"} | json | event_name="pick_submitted" | reserve_used_ms > 0
```

### Derived fields → one-click navigation

The Loki datasource is configured (see [`docs/dev/telemetry/datasources/grafanacloud-logs.json`](../dev/telemetry/datasources/grafanacloud-logs.json)) so the following IDs in any log line become clickable:

| Field | Click action |
|-------|--------------|
| `trace_id` (any spelling: `traceID`, `trace_id`, body or label) | Open the trace in Tempo |
| `ws_conn_id` | Internal Loki query showing every event for that WebSocket from connect → disconnect |
| `user_id` | Internal Loki query for all events involving that user |
| `draft_id` | Internal Loki query for the entire herodraft session |

When debugging a pause complaint, the typical loop is: open Loki → filter by `draft_id` → find the `draft_paused` event → click its `trace_id` → see the `ws.message` → `herodraft.submit_pick` (or pause-endpoint) span in Tempo.

## API Endpoints

### Get Draft State

```
GET /api/herodraft/<draft_id>/
```

Returns full draft state including teams, rounds, and current phase.

### Submit Pick/Ban

```
POST /api/herodraft/<draft_id>/pick/
```

**Request:**
```json
{
  "hero_id": 1
}
```

### Ready Up

```
POST /api/herodraft/<draft_id>/ready/
```

### Flip Coin

```
POST /api/herodraft/<draft_id>/flip/
```

### Make Choice (Pick Order/Side)

```
POST /api/herodraft/<draft_id>/choose/
```

**Request:**
```json
{
  "choice": "first_pick"  // or "second_pick", "radiant", "dire"
}
```

## Frontend Implementation

### File Structure

```
frontend/app/
├── components/herodraft/
│   ├── HeroDraftModal.tsx      # Main modal container (612 lines)
│   ├── DraftTopBar.tsx         # Team info, avatars, timers
│   ├── HeroGrid.tsx            # Hero selection with search
│   ├── DraftPanel.tsx          # Draft timeline visualization
│   ├── HeroDraftHistoryModal.tsx # Event history display
│   ├── hooks/
│   │   └── useHeroDraftWebSocket.ts  # WebSocket connection hook
│   ├── api.ts                  # HTTP API functions
│   ├── schemas.ts              # Zod runtime validation
│   └── types.ts                # TypeScript type definitions
├── store/
│   └── heroDraftStore.ts       # Zustand state store
└── pages/herodraft/
    └── HeroDraftPage.tsx       # Page component
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `HeroDraftModal` | Main container for draft UI |
| `DraftTopBar` | Timer display, team info, turn indicator |
| `HeroGrid` | Hero selection grid with filtering |
| `DraftPanel` | Pick/ban slots display |

### WebSocket Hook (`useHeroDraftWebSocket`)

Manages WebSocket connection with automatic reconnection:

```typescript
interface UseHeroDraftWebSocketOptions {
  draftId: number | null;
  enabled?: boolean;  // Only connect when enabled
  onStateUpdate?: (draft: HeroDraft) => void;
  onTick?: (tick: HeroDraftTick) => void;
  onEvent?: (event: HeroDraftEvent) => void;
}

interface UseHeroDraftWebSocketReturn {
  isConnected: boolean;
  connectionError: string | null;
  reconnectAttempts: number;
  reconnect: () => void;
}
```

**Reconnection Strategy:**
- Base delay: 1000ms
- Max delay: 30,000ms (30s)
- Max attempts: 10
- Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s...

**Message Types Handled:**
- `initial_state` - Full state on connect/reconnect
- `herodraft_event` - Events with optional state update
- `herodraft_tick` - Timer updates every second

### State Management (Zustand)

```typescript
interface HeroDraftState {
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  selectedHeroId: number | null;
  searchQuery: string;

  // Actions
  setDraft: (draft: HeroDraft) => void;
  setTick: (tick: HeroDraftTick) => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;
  reset: () => void;

  // Computed helpers
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
}
```

### Event Handling

Events are processed in `HeroDraftModal.handleEvent()`:

```typescript
switch (event.event_type) {
  case "captain_ready":
    toast.info(`${captainName} is ready`);
    break;
  case "captain_connected":
    toast.success(`${captainName} connected`);
    break;
  case "captain_disconnected":
    toast.warning(`${captainName} disconnected`);
    break;
  case "draft_paused":
    toast.warning("Draft paused - waiting for captain to reconnect");
    setResumeCountdown(null); // Cancel any active countdown
    break;
  case "resume_countdown":
    const seconds = event.metadata?.countdown_seconds ?? 3;
    setResumeCountdown(seconds);
    toast.info(`Resuming in ${seconds}...`);
    break;
  case "draft_resumed":
    toast.success("Draft resumed - all captains connected");
    setResumeCountdown(null);
    break;
  // ... more event types
}
```

### Pause Overlay Implementation

The pause overlay shows in two states:
1. **Waiting** - When `draft.state === "paused"` and no countdown
2. **Countdown** - When `resumeCountdown` is active

```tsx
{(draft.state === "paused" || resumeCountdown !== null) && (
  <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
    {resumeCountdown !== null && resumeCountdown > 0 ? (
      // Countdown state - green text
      <>
        <h2 className="text-3xl font-bold text-green-400">
          Resuming in {resumeCountdown}...
        </h2>
        <p>All captains connected</p>
      </>
    ) : (
      // Waiting state - yellow text
      <>
        <h2 className="text-3xl font-bold text-yellow-400">
          Draft Paused
        </h2>
        <p>Waiting for captain to reconnect...</p>
        <Button onClick={reconnect}>Reconnect</Button>
      </>
    )}
  </div>
)}
```

**Countdown Timer Effect:**

```typescript
useEffect(() => {
  if (resumeCountdown === null || resumeCountdown <= 0) return;

  const timer = setTimeout(() => {
    setResumeCountdown((prev) =>
      prev !== null && prev > 0 ? prev - 1 : null
    );
  }, 1000);

  return () => clearTimeout(timer);
}, [resumeCountdown]);
```

### Pause Overlay Behavior

| Event | Action |
|-------|--------|
| `draft_paused` | Show overlay with "Waiting..." message, cancel any countdown |
| `resume_countdown` | Start countdown from received seconds (usually 3) |
| `draft_resumed` | Clear countdown, overlay hides when state changes to "drafting" |
| `draft_paused` during countdown | Cancel countdown, show waiting message |

### Test IDs

All components have `data-testid` attributes for Playwright testing:

| Test ID | Element |
|---------|---------|
| `herodraft-modal` | Main modal container |
| `herodraft-paused-overlay` | Pause/countdown overlay |
| `herodraft-paused-title` | "Draft Paused" heading |
| `herodraft-countdown-title` | "Resuming in X..." heading |
| `herodraft-reconnect-btn` | Reconnect button |
| `herodraft-reconnecting` | Connection status indicator |
| `herodraft-hero-{id}` | Hero buttons in grid |
| `herodraft-confirm-dialog` | Pick confirmation dialog |

## Testing

### Backend Tests

```bash
just test::run 'python manage.py test app.tests.test_herodraft_consumers -v 2'
```

Key test: `test_pause_resume_timing_adjustment` - verifies that pause duration + countdown is correctly added to `started_at`.

### Frontend E2E Tests (Playwright)

```bash
just test::pw::spec websocket-reconnect-fuzz
```

Fuzz tests verify:
- Timer pauses immediately on disconnect
- Timer resumes correctly after reconnection
- State is maintained through connection drops
- Rapid reconnect cycles don't cause issues
