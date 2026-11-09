- **Shared draft tick runner.** The hero draft's Redis-locked tick loop, heartbeat/connection
  keys and consumer plumbing moved into `app/tasks/draft_tick.py` and `BaseDraftConsumer`
  hooks; the team-draft WebSocket (`DraftConsumer`) now runs on the same base with its own
  `teamdraft` Redis prefix. Hero draft behaviour and payloads are unchanged. Frontend countdown
  math and clock-offset handling moved to `~/lib/draftClock`. Kick, connection-count and
  broadcaster-shutdown log events now carry `system=websocket` instead of `system=herodraft`.
