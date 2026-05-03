# HeroDraft test isolation — fix flaky-recovered E2E specs

**Status:** scaffold / planning
**Branch:** `fix/herodraft-test-isolation`
**Discovered:** 2026-05-03 during local Playwright runs on PR #185

## Symptom

Across two consecutive local Playwright runs on the same SHA, multiple specs fail
on first attempt and recover only on Playwright's automatic retry — except for
`stale-connection.spec.ts:174`, which on the **second** run failed both attempts.
Treating retry-passes as defects, not noise.

| # | File | Test | Run 1 (15.4m) | Run 2 (16.7m) |
|---|---|---|---|---|
| 1 | `frontend/tests/playwright/e2e/herodraft/stale-connection.spec.ts:174` | `client reconnects after WebSocket is force-closed` | retry-passed | **HARD FAIL** |
| 2 | `frontend/tests/playwright/e2e/herodraft/two-captains-full-draft.spec.ts:237` | `@cicd should complete a full draft with both captains via tournament UI` | retry-passed | retry-passed |
| 3 | `frontend/tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts:162` | `should recover draft state after reconnection during drafting phase` | retry-passed | passed clean |
| 4 | `frontend/tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts:410` | `Shuffle Draft - Captain Login Scenarios — should switch captains after a pick in shuffle draft` | n/a | retry-passed (new) |

There are **two distinct root causes**, and the spin-off needs to address each:

## Cause A — captain-leftover-draft banner blocks `view-draft-btn` (covers #2, #3)

The captain user lands on the match page (`/tournament/<pk>/bracket/match/<gpk>`)
but the page renders the global "active hero draft" banner instead of the
start-draft button:

```yaml
- generic:
  - img
  - link:
    - /url: /herodraft/3
    - text: You have an active hero draft - Click to join
  - button: ...
```

`page.getByTestId('view-draft-btn').click()` then times out at 15s.

This banner renders when the captain user has a herodraft in
`pending` / `paused` / `drafting` state on their account — leftover from a prior
test or run that didn't clean up. The reset endpoint exists and
`stale-connection.spec.ts:190` already calls it
(`POST /tests/herodraft/<draftPk>/reset/`), but the setup helpers in
`two-captains-full-draft.spec.ts` and `websocket-reconnect-fuzz.spec.ts` don't.

**Confirmed evidence:** `frontend/test-results/e2e-herodraft-two-captains-a5374--captains-via-tournament-UI-herodraft/error-context.md` shows the banner DOM at the moment of the click timeout.

## Cause B — `waitForEvent('websocket')` doesn't fire after `ws.close(4001)` (covers #1)

Different mechanism. The spec at `stale-connection.spec.ts:174` arms a
`page.waitForEvent('websocket')` listener BEFORE force-closing the existing WS
via `ws.close(4001, 'Simulated stale connection')`, then waits up to 15s for the
client to open a *new* WebSocket. On run 2 that listener never fired:

```
TimeoutError: page.waitForEvent: Timeout 15000ms exceeded
  while waiting for event "websocket"
```

(extracted from `test-results/e2e-herodraft-stale-connec-90f50-r-WebSocket-is-force-closed-herodraft-retry1/trace.zip`)

The `waitForEvent` is registered before the force-close, so it's not a listener-race. Possible causes to investigate:

1. Consumer's `onclose` handler does not call `scheduleReconnect` for close
   code `4001`. Frontend code path: `frontend/app/store/herodraftStore` (or
   wherever the WS manager lives) needs verification — search for
   `scheduleReconnect` and the `intentionalClose` flag the spec comment
   references.
2. Reconnect is attempted but uses a URL the predicate
   `(ws) => ws.url().includes('/api/herodraft/')` doesn't match
   (e.g. switched to `wss://` vs `https://` route, or moved off `/api/`).
3. Reconnect is delayed > 15s (backoff longer than the spec's timeout).
4. The page's `__wsInstances` global the spec writes to was already missing
   the entry (force-close ran on a stale ref and the real WS lived on).
   Verify `frontend/app/lib/wsManager.ts` (or similar) actually pushes every
   live WS into `(window).__wsInstances`.

## Cause C — unknown, chromium project (covers #4)

`08-shuffle-draft/01-full-draft.spec.ts:410` retry-passed for the first time on
run 2. Outside the herodraft project entirely. Trace + screenshot live in
`frontend/test-results/e2e-08-shuffle-draft-01-fu-b5b02-ter-a-pick-in-shuffle-draft-chromium-retry1/`.
Needs its own first-pass investigation before deciding whether it lands in this
spin-off or a separate one. **Don't dismiss as flaky.**

## Per-test rudimentary spec

### 1. `stale-connection.spec.ts:174` — client reconnects after WebSocket is force-closed (Cause B)

**What it should verify:** force-closing the raw WS via `ws.close(4001)`
triggers the consumer's `scheduleReconnect`, a new WS opens, and the draft UI
re-attaches to a connected state.

**Failure mode:**
`TimeoutError: page.waitForEvent: Timeout 15000ms exceeded while waiting for event "websocket"`.
Listener was registered before the force-close, so this is not a listener race
— the client genuinely did not open a reconnection within 15s.

**Investigation steps before fixing:**
- `git grep -n 'scheduleReconnect\|intentionalClose\|__wsInstances'` in
  `frontend/app/` to map the WS lifecycle module.
- Run the spec headed (`just test::pw::headed --grep "client reconnects"`)
  and observe DevTools Network → WS to confirm whether a new WS is attempted.
- If no attempt: bug in the reconnect dispatcher.
- If an attempt to a non-matching URL: bug in the URL builder.
- If an attempt > 15s out: bug in backoff config (or just bump the spec
  timeout, but only if the backoff is intentional).

**Acceptance criteria:**
- Re-run 10× in isolation (`--repeat-each=10`); zero retries needed.
- Root cause is documented (which of the four hypotheses above hit).
- An explicit assertion was added that fails LOUDLY with the inferred
  cause, not a generic timeout. e.g. `expect(reconnectAttempted).toBe(true)`
  before the WS event-wait, with a custom message naming the dispatcher.

### 2. `two-captains-full-draft.spec.ts:237` — full draft with both captains (Cause A)

**What it should verify:** end-to-end happy path — two captains navigate from
tournament UI, both ready, coin flip, full pick/ban, completion.

**Failure mode:** captured in
`frontend/test-results/e2e-herodraft-two-captains-a5374--captains-via-tournament-UI-herodraft/error-context.md`.
Page snapshot shows the active-draft banner blocking `view-draft-btn` on at
least one captain page.

**Acceptance criteria:**
- Add a reset step at spec setup that clears any existing herodrafts owned by
  either captain user before the test navigates.
- Reset must be idempotent and survive a clean populate.
- Re-run 10× in isolation; zero retries needed.

### 3. `websocket-reconnect-fuzz.spec.ts:162` — recover draft state after reconnection (Cause A)

**What it should verify:** after disconnecting and reconnecting mid-draft, the
consumer rehydrates the correct state.

**Failure mode:** `setupCaptain` helper (line 44) times out clicking
`view-draft-btn` — same banner as #2.

**Acceptance criteria:**
- Same captain-reset step as #2, applied via the shared `setupCaptain` helper
  so the fix is one place, not two.
- The fuzz body itself (reconnect timing, jitter) is not the suspect — leave
  that logic alone.

### 4. `08-shuffle-draft/01-full-draft.spec.ts:410` — switch captains after a pick (Cause C)

**What it should verify:** in a shuffle draft, the captain seat advances after
a pick is committed.

**Failure mode:** unknown — only seen as a retry-pass on run 2. First step is
to extract the trace from
`frontend/test-results/e2e-08-shuffle-draft-01-fu-b5b02-ter-a-pick-in-shuffle-draft-chromium-retry1/trace.zip`
(use `unzip -p … test.trace | jq` and look for `type: "after"` entries with
an `error` payload).

**Acceptance criteria:**
- Pin the failure mode (which assertion timed out, which DOM state surfaced).
- Decide whether the cause aligns with A, B, or is its own new C/D/etc.
- Re-run 10× in isolation; zero retries needed.

## Suggested implementation order

1. Cause A first (it covers two specs at once):
   - Move the captain-draft-reset call into a shared helper at
     `frontend/tests/playwright/e2e/herodraft/helpers/resetCaptainDrafts.ts`.
   - Call it from `setupCaptain` in `websocket-reconnect-fuzz.spec.ts` and at
     the top of `two-captains-full-draft.spec.ts`'s describe block.
   - Backend: confirm the existing
     `POST /tests/herodraft/<draftPk>/reset/` endpoint also clears drafts the
     user is a *captain* of, not just the specific draft pk. If not, add a
     `POST /tests/herodraft/clear-user/<userPk>/` test endpoint.
2. Cause B next — needs frontend code spelunking, not just a test fix.
   - Map the WS reconnect lifecycle.
   - Add a public hook the spec can assert on (e.g. expose
     `wsManager.lastReconnectAttempt` on `window` for test-only builds, or
     use `page.evaluate` to read internal state).
   - Fix the underlying defect if there is one.
3. Cause C investigation — extract trace, decide if it belongs here.
4. Re-run all four specs with `--repeat-each=10 --workers=1` to verify zero
   retries.

## Out of scope

- The 4 tests themselves are correct in *what* they assert. Don't rewrite the
  assertions.
- The herodraft consumer / WebSocket layer doesn't need a redesign — only
  whatever specific defect Cause B turns out to be.
- This work is independent of PR #185 (UserCard/TournamentCard tooltip perf)
  — that PR doesn't touch herodraft code.

## Done definition

- All 4 specs pass on the first attempt across 10 consecutive runs.
- No `test.retry` or `test.fixme` left in the specs.
- The shared captain-reset helper has a docstring explaining when to call it
  and what it touches.
- Cause B's underlying defect (or the reason the test was wrong about it) is
  documented in the spec's commit message.

## Memory rule

Per project policy: never describe a failing test as "flaky." Every failure is
a defect in our code or test until proven otherwise. Pass-on-retry behavior is
a *symptom* to investigate, not noise to dismiss.
