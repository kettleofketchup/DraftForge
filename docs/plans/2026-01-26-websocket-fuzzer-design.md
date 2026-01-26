# WebSocket Reconnection Fuzzer Design

**Date:** 2026-01-26
**Branch:** feature/responsiveness
**Status:** Approved

## Problem Statement

The HeroDraft timer does not pause when a captain disconnects. Test evidence:
- Grace timer: 28s → 18s (continued ticking during 5s disconnect)
- Expected: Timer should freeze immediately on any captain disconnect

## Requirements

### Pause Behavior
- **Trigger:** Any captain disconnects → immediate pause
- **Scope:** Affects all clients (captains + spectators)
- **UI:** Full overlay for everyone showing "Waiting for opponent to reconnect..."

### Resume Behavior
- **Trigger:** All captains connected → start countdown
- **Countdown:** "Resuming in 3... 2... 1..." (exactly 3 seconds)
- **Then:** Timer resumes from where it paused

### Timing Tolerances
- Overlay appears: <100ms after disconnect
- Overlay disappears: <100ms after countdown ends
- Timer accuracy: Zero drift during pause

## Architecture

### FuzzOrchestrator Class

```
┌─────────────────────────────────────────────────────────┐
│                   FuzzOrchestrator                       │
├─────────────────────────────────────────────────────────┤
│  - contexts: Map<role, BrowserContext>                  │
│  - timers: { before: TimerState, after: TimerState }    │
│  - scenarios: ScenarioRunner[]                          │
├─────────────────────────────────────────────────────────┤
│  Methods:                                                │
│  - connectCaptain(role: 'A' | 'B')                      │
│  - connectSpectator(id: number)                         │
│  - dropConnection(role: string)                         │
│  - captureTimerState() → TimerState                     │
│  - assertPauseOverlay(visible: boolean, tolerance: ms)  │
│  - assertTimerFrozen(duration: ms)                      │
│  - assertCountdown(seconds: number)                     │
│  - runScenario(scenario: Scenario)                      │
└─────────────────────────────────────────────────────────┘
```

### Timing Data Structures

```typescript
interface TimingEvent {
  type: 'disconnect' | 'reconnect' | 'overlay_show' | 'overlay_hide' | 'countdown_start' | 'countdown_end';
  timestamp: number;  // performance.now() from page
  role: string;
}

interface TimerState {
  graceTime: number;      // seconds remaining
  teamAReserve: number;
  teamBReserve: number;
  capturedAt: number;     // timestamp
}
```

### Timing Measurement Approach

1. Before disconnect: inject MutationObserver watching for `[data-testid="herodraft-paused-overlay"]`
2. Observer records `performance.now()` when overlay becomes visible
3. Compare to disconnect timestamp → must be <100ms
4. Use connected spectator to verify timer freeze (captains get disconnected)

## Test Scenarios

| # | Scenario | Actions | Key Assertions |
|---|----------|---------|----------------|
| 1 | **Single captain drop** | A drops, waits 3s, reconnects | Overlay <100ms, timer frozen, countdown 3-2-1, resume accurate |
| 2 | **Alternating drops** | A drops, reconnects, B drops, reconnects | Each drop triggers pause, each full-reconnect triggers resume |
| 3 | **Simultaneous drops** | A+B drop same time, both reconnect | Single pause period, resume when BOTH back |
| 4 | **Rapid reconnect cycles** | A connects/disconnects 5x in 2 seconds | No race conditions, final state correct |
| 5 | **Drop during countdown** | A reconnects, during "2..." B drops | Countdown cancels, back to paused |
| 6 | **Spectator joins during pause** | Pause active, spectator connects | Spectator sees overlay immediately |
| 7 | **Spectator joins during countdown** | During "2...", spectator connects | Spectator sees countdown synced |

### Assertions Per Scenario

| Assertion | Description |
|-----------|-------------|
| **Timer freeze** | Grace/reserve time values don't change during pause |
| **Immediate pause** | Overlay appears within <100ms of disconnect |
| **Immediate resume UI** | Overlay disappears within <100ms of countdown end |
| **Countdown accuracy** | "3...2...1" takes exactly 3 seconds before timer resumes |
| **Timer continuity** | Timer resumes from where it paused (not reset, not jumped) |
| **State consistency** | Draft state (picks, bans, round) unchanged through pause/resume |
| **Spectator sync** | Spectators see same pause/resume state as captains |

## File Organization

```
tests/playwright/e2e/herodraft/
├── websocket-fuzzer.spec.ts      # Main test file with 7 scenarios
├── helpers/
│   └── FuzzOrchestrator.ts       # Orchestrator class
```

## Required Changes

### Backend (HeroDraftConsumer)

1. **Track connected captains** - Maintain set of connected captain user IDs
2. **On disconnect** - If captain, broadcast `pause` event
3. **On connect** - If all captains connected, broadcast `resume_countdown` event
4. **Timer management** - Store `paused_at` timestamp, calculate remaining time on resume

### Frontend (React/Zustand)

1. **Handle `pause` event** - Show overlay immediately, stop local timer tick
2. **Handle `resume_countdown` event** - Show "Resuming in 3...2...1...", then hide overlay
3. **Sync timer on reconnect** - Use server-provided remaining time

### State Flow

```
Captain A disconnects
  → Backend: is_paused=true, paused_at=now(), broadcast {type: 'pause', reason: 'captain_disconnected'}
  → Frontend: show overlay, freeze timer display

Captain A reconnects (all captains now connected)
  → Backend: broadcast {type: 'resume_countdown', countdown: 3}
  → Frontend: show "Resuming in 3...", tick down, then hide overlay
  → Backend (after 3s): is_paused=false, broadcast {type: 'resumed', timer_state: {...}}
```

## Implementation Order

1. **Backend first** - Add pause/resume events to HeroDraftConsumer
2. **Frontend second** - Add overlay and countdown UI components
3. **Fuzzer last** - Write tests that verify the behavior

## Estimated Scope

- FuzzOrchestrator: ~200 lines
- 7 test scenarios: ~400 lines
- Backend consumer changes: ~100 lines
- Frontend overlay/countdown: ~150 lines
