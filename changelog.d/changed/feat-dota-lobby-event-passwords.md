- One password per event replaces the per-lobby passwords derived from the Django secret
  key. A recreated lobby keeps the event's password; a changed password applies to lobbies
  created afterwards, and existing lobbies keep theirs.
- A tournament created from an event takes its lobby settings from the event and shows them
  read-only; standalone tournaments keep their own.
