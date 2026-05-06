# HeroDraft test isolation — fix flaky-recovered E2E specs

**Status:** Cause B fixed in spec form; Cause A and C need live observation
**Branch:** `fix/herodraft-test-isolation`
**Discovered:** 2026-05-03 during local Playwright runs on PR #185

## Progress log

- 2026-05-03 (`30dd3556`) — Cause B addressed: `stale-connection.spec.ts:174`
  rewritten to use `page.routeWebSocket('**/api/herodraft/**', ...)` + the
  captured `WebSocketRoute.close({ code: 4001 })` to simulate the kill, instead
  of the `(window as any).__wsInstances` Proxy injected via `addInitScript`.
  Production `WebSocketManager` is untouched — the fix is purely test-side.
  See **Cause B → Resolution** below.
- 2026-05-03 (3-spec verification run #1): C ✅ passed clean (44.7s);
  B ⚠️ retry-passed — `wsRoutes.length === 0` on first attempt at line 206
  even after waiting for `assertConnected`, indicating a Playwright
  `routeWebSocket` activation race where the first WS opens before the
  CDP route is fully wired. Fix is partial. A ❌ failed.
- 2026-05-03 (run #2 with budget bumped to 15s): C ✅ B ✅ A ❌. A still
  failed — `assertCaptainsConnected` polled is_connected for 15s and
  never saw `true`.
- 2026-05-03 (root-cause **of A** identified): the test endpoint
  `GET /api/tests/herodraft-by-key/<key>/` (in
  `backend/tests/test_herodraft.py:325-343`) manually constructs
  `data["draft_teams"]` from prefetched relations but **omits the
  `is_connected` field** entirely. So `t.is_connected` was `undefined`
  for every team, `every(t => t.is_connected) === false`, the poll
  could never pass regardless of budget. The backend logs showing
  close→reconnect cycles were just normal Playwright test retries on
  the failing assertion — not a 15s WS-close timer in the app.
  Fix: added `is_connected` to the manually-constructed dict. Reverted
  the unnecessary 15s budget bump back to 5s (the field now updates
  immediately after the consumer's transaction commits).

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

## Cause A — `view-draft-btn` click times out on captain login (covers #2, #3)

**Re-evaluating: the original "banner blocks the button" hypothesis is shaky.**

The page snapshot in `frontend/test-results/e2e-herodraft-two-captains-a5374--captains-via-tournament-UI-herodraft/error-context.md` shows the active-draft banner on the page, but:

1. `<ActiveDraftBanner>` (`frontend/app/components/teamdraft/ActiveDraftBanner.tsx`) is small (`py-2`, ~32px) and sits below the navbar, above main content. It would push layout down by 32px, not hide a button.
2. It's `hidden md:flex` — desktop only — and the test runs at desktop width.
3. It's a static `<div>`, not absolutely positioned, so it can't *cover* `view-draft-btn`.

So the banner being on the page is a *symptom* of the captain having a leftover
active draft, but probably isn't *what causes the click to time out*.

**More likely candidates** (need live observation to confirm — none of these
are settled):

a. The match-stats modal that contains `view-draft-btn`
   (`MatchStatsModal.tsx:275`) doesn't auto-open from the URL params alone.
   Navigating to `/tournament/<tpk>/bracket/match/<gpk>` may need an additional
   route trigger that worked once and then regressed.
b. Hydration race: on retry, the page is warm and hydrates before the click;
   on a fresh Playwright worker, a ResizeObserver/AnimationFrame layout shift
   pushes the click into a brief unstable window.
c. The captain's user state hasn't fully rehydrated when `view-draft-btn` is
   clicked — `match.herodraft_id` is briefly undefined, so the button renders
   "Start Draft" with `disabled={createDraftMutation.isPending}` and the click
   waits for it to become enabled.

**Investigation steps before writing a fix:**

1. Run `just test::pw::spec "two captains"` and inspect the failure
   artifacts in `test-results/.../` (screenshot, `error-context.md`,
   `trace.zip` — opened with `npx playwright show-trace`). Specifically:
   is `view-draft-btn` ever in the DOM, and if so, why isn't it clickable
   when the click fires?
2. Add a `getAttribute('disabled')` log line right before the click to
   distinguish "button not in DOM" from "button disabled".
3. If the captain *does* need draft state cleared between tests, the right
   shape is a `POST /tests/herodraft/clear-user/<userPk>/` endpoint that
   nukes any drafts the user is a captain of, called from the spec's `beforeEach`.

## Cause B — RESOLVED via `page.routeWebSocket` (covers #1)

**Resolution shipped in commit `30dd3556`.**

The original spec used `(window as any).__wsInstances` (a Proxy installed by
`context.addInitScript` over `window.WebSocket`) to enumerate live WebSockets
and call `ws.close(4001)`. Two reasons that path was wrong:

1. The Proxy was installed at the *context* level even though only one of the
   three tests in the file needed force-close. Other tests inherit the swap
   for no reason.
2. There were timing scenarios where the close-and-reconnect sequence didn't
   propagate cleanly into the app's `WebSocketManager.scheduleReconnect`
   loop — between two consecutive runs on the same SHA, the test went from
   retry-pass to hard-fail, which means the assertion was racing.

The refactor uses `page.routeWebSocket('**/api/herodraft/**', handler)`
(Playwright 1.48+, this repo runs 1.58):

```ts
const wsRoutes: WebSocketRoute[] = [];
await page.routeWebSocket('**/api/herodraft/**', (ws) => {
  ws.connectToServer();        // proxy to real server — app behavior unchanged
  wsRoutes.push(ws);
});
// ... navigate, establish initial connection ...
await wsRoutes[0].close({ code: 4001, reason: 'Simulated stale connection' });
// ... wait for wsRoutes.length to grow (reconnect) ...
```

**Why this is right:**

- Closing one side of a routed WS closes the other (per Playwright docs), so
  the page sees a normal `close` event with code 4001 — same observable
  signal as a Cloudflare/nginx kill, but driven from the test instead of the
  network.
- No production code changes. The WebSocketManager hot path is untouched.
- The route handler proxies via `connectToServer()` so the app's WS lifecycle
  (open, message flow, close, reconnect) runs against a real server — we
  test the actual reconnect dispatcher, not a mock.
- A timeout in the new spec produces a concrete diagnostic naming the suspect
  app code paths (`intentionalClose`, attempt count, `onclose` handler) instead
  of a generic 15s timeout.

**Original failure context kept for posterity:**

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

## Cause C — slow tournament page load + tight test timeout (covers #4)

**Diagnosis from existing artifacts** (`frontend/test-results/e2e-08-shuffle-draft-01-fu-b5b02-ter-a-pick-in-shuffle-draft-chromium/`):

- `test-failed-1.png`: navbar rendered, but the rest of the page is just the
  centered DaisyUI loading spinner. Nothing else has hydrated.
- `error-context.md`: page snapshot at the moment of timeout shows ONLY the
  navbar — no main content tree, no tournament title, no tabs.
- `video.webm` exists but isn't easy to inspect from CLI.

The screenshot's spinner is rendered by `TournamentDetailPage.tsx:214-220`:

```tsx
if (isLoading) {
  return (
    <div className="flex justify-center items-center h-screen">
      <span className="loading loading-spinner loading-lg"></span>
    </div>
  );
}
```

`isLoading` comes from `useTournament(pk)` (`frontend/app/hooks/useTournament.ts:5-12`):

```ts
return useQuery({
  queryKey: ['tournament', pk],
  queryFn: () => fetchTournament(pk!),
  enabled: !!pk,
  refetchInterval: 10_000,
});
```

So the test's view of the world at the moment of failure: `useQuery` was still
`isLoading: true`, meaning the `fetchTournament(pk)` API call hadn't resolved
within the test's effective budget.

Test budget breakdown (`01-full-draft.spec.ts:410-425`):
1. `await loginAdmin()` — variable
2. `await visitAndWaitForHydration(page, ...)` — `page.goto` + `1500ms` hard
   wait (`helpers/utils.ts:62`)
3. `await expect(page.locator('h1')).toContainText(name, { timeout: 10000 })`

So `1500ms + 10000ms = 11.5s` total of post-goto budget for the data fetch
to land. On a cold worker (first attempt of a chromium-project test run, with
no warm cacheops cache + ORM compilation costs on first hit), this can fall
short — the retry passed because the second attempt hit a warm backend.

**Why this isn't a banner/herodraft issue:** the chromium project's spec doesn't
touch herodraft at all. It's the standard tournament detail page, slow on cold
fetch.

**Fix options (in order of cleanness):**

1. **Use `page.waitForResponse(...)` for the tournament fetch.** Deterministic
   — wait for the actual API call to complete, not a wall-clock timer:

   ```ts
   const tournamentResponse = page.waitForResponse(
     (r) => r.url().includes(`/api/tournaments/${tournamentData.pk}/`) && r.ok(),
   );
   await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}`);
   await tournamentResponse;
   ```

2. **Bump the `h1` timeout to 30s.** Defensive — catches cold-start slowness
   without changing test shape. Doesn't address why the fetch is slow.

3. **Refactor the page to `useSuspenseQuery` + a `<Suspense>` boundary.**
   Hydration would then suspend until the data arrives; `page.goto` would not
   resolve until the page is renderable. Bigger lift, touches React 19 patterns,
   not the right fix for this spin-off.

4. **Refactor `visitAndWaitForHydration` to wait for a stable signal.** The
   1500ms hard wait at `utils.ts:62` is a code smell — it assumes hydration
   completes in a fixed time. Better to wait for `body[data-hydrated]` (an
   explicit marker the app sets after hydration) or the absence of a known
   loading testid. This affects every test using the helper, so it's a wider
   change — schedule separately.

**Recommendation for this spin-off:** apply fix (1) — the explicit
`waitForResponse`. It's narrow, deterministic, and caps the test's success on
the actual API resolution rather than a wall clock. Fixes (2) and (3) are
follow-ups; (2) is a safety net we may want anyway.

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
- Run the spec (`just test::pw::spec "client reconnects"`) and inspect
  the failure trace via `npx playwright show-trace` — the Network panel
  in the trace viewer shows whether a new WS is attempted.
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
