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
