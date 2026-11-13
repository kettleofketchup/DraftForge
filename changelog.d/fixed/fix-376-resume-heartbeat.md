- **Resume could stay enabled for a disconnected captain.** If the active captain
  reconnected to a paused team draft and their heartbeats then stopped, viewers kept
  seeing them as connected and the Resume button stayed enabled. A paused draft now
  re-announces stale captains every few seconds, so Resume disables again (#376).
