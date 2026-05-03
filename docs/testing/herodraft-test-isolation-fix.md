# HeroDraft test isolation — fix 3 failing E2E specs

**Status:** scaffold / planning
**Branch:** `fix/herodraft-test-isolation`
**Discovered:** 2026-05-03 during local Playwright run on PR #185

## Symptom

Three herodraft E2E tests fail on first attempt and only pass on Playwright's automatic retry. They share a single visible root cause and need test-isolation work, not a code change in the herodraft feature itself.

| # | File | Test |
|---|---|---|
| 1 | `frontend/tests/playwright/e2e/herodraft/stale-connection.spec.ts:174` | `client reconnects after WebSocket is force-closed` |
| 2 | `frontend/tests/playwright/e2e/herodraft/two-captains-full-draft.spec.ts:237` | `@cicd should complete a full draft with both captains via tournament UI` |
| 3 | `frontend/tests/playwright/e2e/herodraft/websocket-reconnect-fuzz.spec.ts:162` | `should recover draft state after reconnection during drafting phase` |

## Shared root cause (confirmed for #2 and #3, suspected for #1)

The captain user lands on the match page (`/tournament/<pk>/bracket/match/<gpk>`) but the page renders the global "active hero draft" banner instead of the start-draft button:

```yaml
- generic:
  - img
  - link:
    - /url: /herodraft/3
    - text: You have an active hero draft - Click to join
  - button: ...
```

`page.getByTestId('view-draft-btn').click()` then times out at 15s.

This banner renders when the captain user has a herodraft in `pending`/`paused`/`drafting` state on their account — a left-over from a prior test or a prior run that wasn't reset.

The reset endpoint exists and `stale-connection.spec.ts:190` already calls it (`POST /tests/herodraft/<draftPk>/reset/`), but `two-captains-full-draft` and `websocket-reconnect-fuzz` setup helpers don't.

## Per-test rudimentary spec

### 1. `stale-connection.spec.ts:174` — client reconnects after WebSocket is force-closed

**What it should verify:** force-closing the raw WS via `ws.close(4001)` triggers the consumer's `scheduleReconnect`, a new WS opens, and the draft UI re-attaches to a connected state.

**Failure mode in last run:** unknown — the `tail -50` truncation lost the message before this test's report was captured. Suspected: the reset call at line 190 runs but `setupSpectator` then races against the reset's commit, OR `waitForConnection(15000)` after reconnect hits the same banner-state issue if the captain user has another draft active.

**Acceptance criteria for the fix:**
- Re-run the test 10× in isolation (`--repeat-each=10`); zero retries needed.
- The reset call must complete (await response status 200) before `setupSpectator` navigates.
- Add an explicit assertion that the start-draft button (or whatever `setupSpectator` clicks) is visible *before* clicking, with a clear error if the banner shows up instead.

### 2. `two-captains-full-draft.spec.ts:237` — full draft with both captains

**What it should verify:** end-to-end happy path — two captains navigate from tournament UI, both ready, coin flip, full pick/ban, completion.

**Failure mode in last run:** captured in `frontend/test-results/e2e-herodraft-two-captains-a5374--captains-via-tournament-UI-herodraft/error-context.md`. The page snapshot shows the active-draft banner blocking `view-draft-btn`. Both captain pages hit this — hardcoded captains have leftover drafts.

**Acceptance criteria for the fix:**
- Add a reset step at spec setup that clears any existing herodrafts owned by either captain user before the test navigates.
- The reset must be idempotent and survive being run on a clean populate.
- Re-run 10× in isolation; zero retries needed.

### 3. `websocket-reconnect-fuzz.spec.ts:162` — recover draft state after reconnection

**What it should verify:** after disconnecting and reconnecting mid-draft, the consumer rehydrates the correct state.

**Failure mode in last run:** identical to #2 — `setupCaptain` helper (line 44 in the same file) times out clicking `view-draft-btn`. The captain has a leftover draft.

**Acceptance criteria for the fix:**
- Same captain-reset step as #2, applied via the shared `setupCaptain` helper so the fix is one place, not two.
- The fuzz body itself (reconnect timing, jitter) is not the suspect — leave the fuzz logic alone.

## Suggested implementation order

1. Move the captain-draft-reset call into a shared helper (e.g. `frontend/tests/playwright/e2e/herodraft/helpers/resetCaptainDrafts.ts`).
2. Call it from `setupCaptain` in `websocket-reconnect-fuzz.spec.ts` and at the top of `two-captains-full-draft.spec.ts`'s describe block.
3. Re-run all three tests with `--repeat-each=10 --workers=1` to verify zero retries.
4. Backend side: confirm the existing `POST /tests/herodraft/<draftPk>/reset/` endpoint also clears drafts the user is a *captain* of, not just the specific draft pk. If not, add a `POST /tests/herodraft/clear-user/<userPk>/` test endpoint that nukes all drafts owned by a user.

## Out of scope

- The 3 tests themselves are correct in *what* they assert. Don't rewrite the assertions.
- The herodraft consumer / WebSocket layer doesn't need changes for this work.
- This work is independent of PR #185 (UserCard/TournamentCard tooltip perf) — that PR doesn't touch herodraft code.

## Done definition

- All 3 specs pass on the first attempt across 10 consecutive runs.
- No `test.retry` or `test.fixme` left in the specs.
- The shared captain-reset helper has a docstring explaining when to call it and what it touches.
