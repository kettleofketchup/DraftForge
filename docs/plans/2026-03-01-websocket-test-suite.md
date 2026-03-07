# WebSocket Test Suite Design

**Date**: 2026-03-01
**Branch**: `fix/websocket-reconnect-and-nginx-timeout` (related PR #158)
**GitHub Issue**: #157

## Overview

Comprehensive WebSocket test suite for team draft and herodraft, covering connection lifecycle, real-time state updates, toast notifications, reconnection after drop, multi-browser scenarios, idle timeout, and draft completion. Prioritizes Playwright E2E tests with backend DraftConsumer unit tests.

## Motivation

- Team draft has **zero** WebSocket-specific tests
- DraftConsumer has **zero** backend consumer tests (vs HeroDraft's 13+)
- PR #158 fixed race conditions in WS connect guard and stale closure bugs — need regression coverage
- Reconnection after drop is the hardest scenario to test manually

## Architecture

### Test Layers

| Layer | Scope | Tools |
|-------|-------|-------|
| **Playwright E2E** (priority) | 7 categories, team draft first | Multi-browser contexts, WS interception, test endpoints |
| **Backend Consumer** | DraftConsumer unit tests | `WebsocketCommunicator`, `async_to_sync` |

### New Infrastructure

| File | Purpose |
|------|---------|
| `backend/app/tests/test_draft_consumers.py` | DraftConsumer unit tests (currently 0) |
| `backend/tests/test_draft.py` | Kill-WS test endpoint (follows `test_herodraft.py` pattern) |
| `backend/tests/urls.py` | Register new draft test endpoints |
| `frontend/tests/playwright/helpers/DraftWebSocketHelper.ts` | WS monitoring/reconnection helper (complements TournamentPage) |
| `frontend/tests/playwright/fixtures/teamdraft.ts` | Draft setup/reset/kill-ws fixtures |
| `frontend/tests/playwright/fixtures/index.ts` | Export new fixtures |
| `frontend/tests/playwright/e2e/07-draft/04-websocket-lifecycle.spec.ts` | Connection lifecycle tests |
| `frontend/tests/playwright/e2e/07-draft/05-websocket-reconnect.spec.ts` | Reconnection tests (`test.describe.serial()`) |
| `frontend/tests/playwright/e2e/07-draft/06-websocket-toasts.spec.ts` | Toast notification tests |

### Existing Infrastructure to Build On

- `HeroDraftPage.ts` — page object pattern with `waitForConnection()`, phase assertions
- `herodraft.ts` fixtures — `getHeroDraftByKey()`, `resetHeroDraft()`, multi-captain setup
- `test_herodraft_consumers.py` — 13 test methods using `WebsocketCommunicator`
- `websocket-reconnect-fuzz.spec.ts` — existing HeroDraft reconnection stress tests
- Test endpoint pattern: `/api/tests/herodraft-by-key/<key>/`, `/api/tests/herodraft/<id>/reset/`

---

## Playwright E2E Tests (7 Categories)

### Category 1: Connection Lifecycle

**File**: `07-draft/04-websocket-lifecycle.spec.ts`

| Test | Description |
|------|-------------|
| `connects on modal open` | WS connection established when draft modal opens |
| `disconnects on modal close` | WS cleanly disconnects when modal closes |
| `no duplicate connections` | StrictMode double-mount doesn't create multiple WS connections |
| `clean disconnect on navigation` | Navigating away from page disconnects WS |
| `reconnects on modal reopen` | Closing and reopening modal establishes fresh connection |

**Implementation approach:**
- Monitor WebSocket connections via `page.on('websocket')` event
- Track connect/disconnect events with counters
- Assert exactly 1 connection per modal open
- Use `ws.on('close')` to verify clean disconnect

```typescript
test('connects on modal open', async ({ page }) => {
  const wsConnections: WebSocket[] = [];
  page.on('websocket', (ws) => {
    if (ws.url().includes('/api/draft/')) wsConnections.push(ws);
  });

  await openDraftModal(page);
  expect(wsConnections).toHaveLength(1);
  expect(wsConnections[0].isClosed()).toBe(false);
});
```

### Category 2: Real-time State Updates

**File**: `07-draft/04-websocket-lifecycle.spec.ts` (grouped with lifecycle)

| Test | Description |
|------|-------------|
| `pick updates via WS` | Captain picks player, viewer sees updated draft rounds |
| `users_remaining decrements` | Remaining player count updates after pick via WS |
| `captain assignment shows` | Next captain indicator updates via WS |
| `draft_state hydration` | `_users` dict resolves slim pk-only references |

**Implementation approach:**
- Two browser contexts: one captain (picks), one viewer (observes)
- Viewer asserts UI changes without page refresh
- Verify state update timing (should appear within 2s of pick)

### Category 3: Toast Notifications

**File**: `07-draft/06-websocket-toasts.spec.ts`

| Test | Description |
|------|-------------|
| `player_picked toast` | Rich toast with avatar appears on viewer's screen |
| `draft_started toast` | Info toast when draft begins |
| `draft_completed toast` | Completion toast when all rounds filled |
| `no toast on initial_events` | Historical events on reconnect don't trigger toasts |
| `toast has correct content` | Player name, captain name, pick number in toast |

**Implementation approach:**
- Use `page.locator('[data-sonner-toast]')` to detect toasts
- Verify toast text content matches expected format
- Assert toast appears within 3s of the WS event

```typescript
test('player_picked shows rich toast', async ({ captainPage, viewerPage }) => {
  // Captain picks a player
  await captainPage.pickPlayer('TestPlayer');

  // Viewer should see toast
  const toast = viewerPage.locator('[data-sonner-toast]');
  await expect(toast).toBeVisible({ timeout: 5000 });
  await expect(toast).toContainText('Picked TestPlayer');
});
```

### Category 4: Reconnection After Drop (Highest Priority)

**File**: `07-draft/05-websocket-reconnect.spec.ts`

| Test | Description |
|------|-------------|
| `reconnects after server kill` | Backend kills WS → client reconnects automatically |
| `state consistent after reconnect` | `initial_events` replayed, draft state matches |
| `reconnecting indicator shown` | UI shows reconnecting state during backoff |
| `picks during disconnect received` | Events made while disconnected arrive on reconnect |
| `fallback polling activates` | When WS stays down, polling interval starts |
| `exponential backoff` | Reconnect attempts use increasing delays |

**Implementation approach:**
- Use `POST /api/tests/draft/<id>/kill-ws/` to force-disconnect
- Monitor `page.on('websocket')` for reconnection
- Compare draft state before/after reconnect
- Verify reconnecting indicator visibility

```typescript
test('reconnects after server kill', async ({ page, request }) => {
  const wsEvents: string[] = [];
  page.on('websocket', (ws) => {
    wsEvents.push('open');
    ws.on('close', () => wsEvents.push('close'));
  });

  await openDraftModal(page);
  await expect(wsEvents).toContain('open');

  // Kill connection server-side
  await request.post(`/api/tests/draft/${draftId}/kill-ws/`);

  // Should see close + new open (reconnect)
  await page.waitForTimeout(3000); // Allow backoff
  const opens = wsEvents.filter(e => e === 'open');
  expect(opens.length).toBeGreaterThanOrEqual(2);
});
```

### Category 5: Multi-browser

**File**: `07-draft/04-websocket-lifecycle.spec.ts` (grouped with lifecycle)

| Test | Description |
|------|-------------|
| `two viewers see same updates` | Both browser contexts receive same WS events |
| `captain picks, viewer sees` | Captain action reflected in viewer's UI |
| `spectator has no controls` | Non-captain viewer has read-only UI |

### Category 6: Idle Timeout

**File**: `07-draft/05-websocket-reconnect.spec.ts` (grouped with reconnect)

| Test | Description |
|------|-------------|
| `connection survives 90s idle` | WS stays open beyond old 60s Nginx default |
| `reconnects on timeout boundary` | If connection does drop, automatic reconnect works |

**Implementation approach:**
- `test.slow()` marker for extended timeout
- Keep WS idle for >60s, verify still connected
- Monitor for unexpected close events

### Category 7: Draft Completion via WS

**File**: `07-draft/04-websocket-lifecycle.spec.ts` (grouped with lifecycle)

| Test | Description |
|------|-------------|
| `draft_completed event received` | WS sends completion event when all rounds filled |
| `final state has all choices` | Last `draft_state` has every round with a choice |
| `auto-refresh fires once` | Final refresh triggered after completion |

---

## Backend DraftConsumer Tests

**File**: `backend/app/tests/test_draft_consumers.py`

Mirrors `test_herodraft_consumers.py` pattern (762 lines, 13 methods). DraftConsumer is read-only (no captain tracking, no pause/resume), so tests focus on connection and event forwarding.

### Test Methods

```python
class DraftConsumerTestCase(TransactionTestCase):
    """Tests for the team draft WebSocket consumer."""

    # Connection
    async def test_connect_valid_draft(self):
        """WebSocket connects and receives initial_events with draft_state."""

    async def test_connect_invalid_draft(self):
        """Rejects connection for non-existent draft IDs."""

    async def test_connect_completed_draft(self):
        """Can connect to completed drafts (read-only replay)."""

    # Initial Events
    async def test_initial_events_payload(self):
        """initial_events contains all draft events in order."""

    async def test_initial_events_include_draft_state(self):
        """draft_state in initial_events has rounds, users_remaining, tournament."""

    async def test_draft_state_has_users_dict(self):
        """_users dict present for slim state hydration."""

    # Event Forwarding
    async def test_draft_event_forwarded(self):
        """Channel layer draft.event message reaches connected client."""

    async def test_draft_state_in_forwarded_event(self):
        """Forwarded events include updated draft_state."""

    async def test_player_picked_event_payload(self):
        """player_picked event has captain_name, picked_name, pick_number."""

    # Disconnect
    async def test_disconnect_clean(self):
        """No errors on clean disconnect."""

    async def test_force_disconnect(self):
        """force_disconnect handler closes connection with code 1012."""

    # Multiple Clients
    async def test_multiple_spectators_receive_events(self):
        """Multiple connected clients all receive the same broadcast events."""
```

### Setup Pattern

```python
def get_application(self):
    return URLRouter([
        path("api/draft/<int:draft_id>/", DraftConsumer.as_asgi()),
    ])

async def connect_to_draft(self, draft_id, user=None):
    communicator = WebsocketCommunicator(
        self.get_application(),
        f"/api/draft/{draft_id}/",
    )
    if user:
        communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    self.assertTrue(connected)
    # Read initial_events message
    response = await asyncio.wait_for(
        communicator.receive_json_from(), timeout=5
    )
    return communicator, response
```

---

## Backend Test Endpoint: Kill WS

**Endpoint**: `POST /api/tests/draft/<id>/kill-ws/`
**Location**: `backend/tests/test_draft.py` (new file, follows `test_herodraft.py` pattern)

### Implementation

Uses function-based views with decorators (matches existing test endpoint pattern):

```python
# backend/tests/test_draft.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

from common.utils import isTestEnvironment


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def kill_draft_websocket(request, draft_id):
    """Test-only: force-disconnect all WS clients for a draft."""
    if not isTestEnvironment(request):
        return Response(status=404)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"draft_{draft_id}",
        {"type": "force.disconnect"},
    )
    return Response({"killed": True})
```

### Consumer Handler

Add to `DraftConsumer` in `consumers.py`:

```python
async def force_disconnect(self, event):
    """Test-only: server-initiated connection close."""
    await self.close(code=1012)  # Service Restart
```

### URL Registration

```python
# In backend/tests/urls.py — add import and path
from .test_draft import kill_draft_websocket

path("draft/<int:draft_id>/kill-ws/", kill_draft_websocket, name="test-draft-kill-ws"),
```

---

## DraftWebSocketHelper

**File**: `frontend/tests/playwright/helpers/DraftWebSocketHelper.ts`

Complements the existing `TournamentPage` (which handles navigation, tabs, draft modal). This helper focuses on WS-specific monitoring and assertions.

```typescript
export class DraftWebSocketHelper {
  private wsConnections: WebSocket[] = [];
  private wsMessages: Array<{ type: string; data: unknown }> = [];

  constructor(private page: Page) {
    // Auto-register WS listener on construction
    page.on('websocket', (ws) => {
      if (ws.url().includes('/api/draft/')) {
        this.wsConnections.push(ws);
        ws.on('framereceived', (frame) => {
          try {
            const data = JSON.parse(frame.payload as string);
            this.wsMessages.push(data);
          } catch {}
        });
      }
    });
  }

  // Connection monitoring
  get connectionCount(): number
  get activeConnections(): WebSocket[]
  get messages(): Array<{ type: string; data: unknown }>

  // Assertions
  async assertSingleConnection(): Promise<void>
  async assertNoConnections(): Promise<void>
  async waitForConnection(timeout?: number): Promise<void>
  async waitForReconnect(timeout?: number): Promise<void>
  async waitForMessage(type: string, timeout?: number): Promise<unknown>

  // Toast assertions (wraps Sonner locators)
  async waitForToast(text: string, timeout?: number): Promise<Locator>
  async assertNoToast(duration?: number): Promise<void>

  // Reset
  reset(): void  // Clear tracked connections/messages
}
```

---

## Team Draft Fixtures

**File**: `frontend/tests/playwright/fixtures/teamdraft.ts`

```typescript
export const teamDraftFixtures = {
  getDraftByKey: async (context: APIRequestContext, key: string) => { ... },
  resetDraft: async (context: APIRequestContext, draftId: number) => { ... },
  killWebSocket: async (context: APIRequestContext, draftId: number) => { ... },
};
```

---

## Test Data Strategy

**Reuse existing tournament data** with reset endpoints rather than creating isolated WS-test-only data. The WS tests verify _connection behavior_, not tournament data integrity.

### Existing Tournaments to Use

| Key | State | Purpose |
|-----|-------|---------|
| `draft_captain_turn` | Mid-draft, captain has pending pick | Connection lifecycle, pick WS events, toasts |
| `shuffle_tie_resolution` | Shuffle draft with tie pending | Shuffle-specific WS tests |

### Reset Strategy

Use `resetTournamentByKey(context, key)` in `test.beforeEach()` to ensure clean state:

```typescript
test.beforeEach(async ({ context }) => {
  await resetTournamentByKey(context, 'draft_captain_turn');
});
```

### New Test Data (if existing tournaments insufficient)

If we need a tournament specifically in "not started" state, add a `DynamicTournamentConfig` to `backend/tests/data/tournaments.py`:

```python
WS_TEST_SNAKE_DRAFT = DynamicTournamentConfig(
    pk=107,  # Next available
    name="WS Test Snake Draft",
    user_count=8,
    team_count=2,
    tournament_type="single_elimination",
    league_name=TEST_LEAGUE_NAME,
)
```

This auto-creates via the existing `populate_tournaments()` function — no new populate file needed.

---

## Implementation Order

### Phase 1: Backend Infrastructure
1. **Backend test endpoint** — `backend/tests/test_draft.py` with `kill_draft_websocket` + register in `urls.py`
2. **Consumer handler** — Add `force_disconnect()` to `DraftConsumer` in `consumers.py`
3. **Backend DraftConsumer tests** — `backend/app/tests/test_draft_consumers.py`

### Phase 2: Playwright Infrastructure
4. **DraftWebSocketHelper** — `frontend/tests/playwright/helpers/DraftWebSocketHelper.ts`
5. **Team draft fixtures** — `frontend/tests/playwright/fixtures/teamdraft.ts` + export from `index.ts`

### Phase 3: E2E Tests (priority order)
6. **Category 4: Reconnection tests** (highest priority — validates PR #158 fix, `test.describe.serial()`)
7. **Category 1: Connection lifecycle tests**
8. **Category 3: Toast notification tests**
9. **Category 2: Real-time state update tests** (requires multi-browser)
10. **Category 5: Multi-browser tests** (can merge with Cat 2)
11. **Category 7: Draft completion tests**
12. **Category 6: Idle timeout tests** (last — requires `test.slow()`)

---

## HeroDraft Extensions (Phase 2)

After team draft tests are solid, extend coverage to herodraft:

- Add `kill-ws` endpoint for herodraft channel group (`herodraft_{id}`)
- Add reconnection tests to existing `websocket-reconnect-fuzz.spec.ts`
- Add toast tests for herodraft events (hero picks, timer ticks)
- Backend: extend `test_herodraft_consumers.py` with `force_disconnect` test

---

## Success Criteria

- [ ] DraftConsumer has >=8 backend consumer tests passing
- [ ] All 7 Playwright test categories have at least 1 passing test
- [ ] Reconnection after server-kill works reliably in CI
- [ ] No flaky tests — WS tests use proper waits, not `waitForTimeout`
- [ ] Toast notifications verified for all 3 significant events
- [ ] CI sharding works with new test files (balanced across shards)
