# Hero Draft (Captain's Mode)

The Hero Draft system implements Dota 2's Captain's Mode for tournament matches, allowing team captains to ban and pick heroes in real-time via WebSocket.

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
| `paused` | Draft paused due to captain disconnect |
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

During drafting phase, the server broadcasts `herodraft_tick` every second:

```json
{
  "type": "herodraft_tick",
  "current_round": 0,
  "active_team_id": 123,
  "grace_time_remaining_ms": 25000,
  "team_a_id": 123,
  "team_a_reserve_ms": 90000,
  "team_b_id": 456,
  "team_b_reserve_ms": 85000
}
```

## Pause/Resume System

### Trigger Conditions

The draft **pauses immediately** when:
- Any captain disconnects during the `drafting` phase
- This ensures fairness - no picks can be made while a captain is absent

The draft **resumes** when:
- All captains are reconnected
- A 3-second countdown is shown before timer resumes

### Backend Logic

**On Captain Disconnect (during DRAFTING):**

1. Set `draft.state = PAUSED`
2. Store `draft.paused_at = now()`
3. Broadcast `draft_paused` event to all clients
4. Tick broadcaster stops (checks state != DRAFTING)

**On All Captains Reconnected (during PAUSED):**

1. Calculate `pause_duration = now() - draft.paused_at`
2. Broadcast `resume_countdown` with `{countdown_seconds: 3}`
3. Adjust active round's `started_at` forward by `pause_duration + 3 seconds`
4. Set `draft.state = DRAFTING`, clear `paused_at`
5. Broadcast `draft_resumed` event
6. Restart tick broadcaster

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
inv test.run --cmd 'python manage.py test app.tests.test_herodraft_consumers -v 2'
```

Key test: `test_pause_resume_timing_adjustment` - verifies that pause duration + countdown is correctly added to `started_at`.

### Frontend E2E Tests (Playwright)

```bash
inv test.playwright.spec --file tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts
```

Fuzz tests verify:
- Timer pauses immediately on disconnect
- Timer resumes correctly after reconnection
- State is maintained through connection drops
- Rapid reconnect cycles don't cause issues
