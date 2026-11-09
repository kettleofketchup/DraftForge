- Team-draft broadcasts, the initial WebSocket state and draft endpoint responses now build
  the draft state in a fixed number of queries (about 17) regardless of team, round or user
  count; previously each broadcast of a 4-team draft took about 140 queries and grew with
  every team. A pick now costs 70 queries instead of about 540.
- Team-draft pick, undo, ready, start, pause and resume no longer answer 500 when a
  WebSocket broadcast fails after the change has been saved; the failure is logged as
  `broadcast_after_commit_failed` and the remaining post-commit work (cache invalidation,
  tick start) still runs.
- Undoing a pick in a snake or normal draft no longer leaves the next round without a
  captain.
- Backend tests use a fast password hasher under the test runner, cutting the team-draft
  test modules from about 6 minutes to about 35 seconds.
- The tournament page no longer flips a captain's lobby toggle back to "Ready up" after they
  ready up. A tournament fetch that was already reading when the ready change committed
  cached its older copy for up to 10 minutes, and every later refetch served it.
- A team or hero draft whose sockets stayed open for five minutes without anyone connecting
  or leaving no longer stops its clock. The connection count expired after 300 seconds and
  the tick loop then stopped with `no_connections`; open sockets now refresh their entry
  every 10 seconds.
- While a team draft is paused, a captain whose heartbeats stop is now shown as disconnected
  and Resume stays disabled. Freshness was only re-checked by the clock loop, which stopped
  at the pause, so a captain who went quiet mid-pause kept showing as connected.
- A burst of team-draft events (a timeout sends up to five) no longer freezes the draft
  page for several seconds. The page now applies a burst in one update, skips users that
  have not changed, refetches the tournament once per burst and not at all when the open
  draft socket already carries the new state, and never lets an older draft state replace
  a newer one.
