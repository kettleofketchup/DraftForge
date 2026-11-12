- **Team-draft pick timer (backend).** Tournaments gain `draft_options` (grace and reserve
  time, default 30 s each; the timer is on for new tournaments). When enabled, rounds are built
  into a ready lobby that staff start (or force-start), each pick runs a server-authoritative
  grace + reserve clock broadcast as `draft_tick`, captains and staff can pause/resume, the
  draft auto-pauses when the active captain's connection goes stale, and an expired pick is
  skipped (`skip_turn`: swapped with the next pick; shuffle re-selects the captain). Pick
  durations, reserve use and skips are recorded on each round. Existing drafts and all demo
  fixtures stay untimed.
