- Organizer and player controls for dota_lobby lobbies (#56). The match dialog shows a game's
  lobby state, and to its players and tournament staff the lobby name, password and each
  player's invite and seat status, with the name above its status so long names stay readable.
  Staff can create, retry, recreate, close and launch the lobby and re-invite players, and
  players can invite themselves. Invite actions show only while someone is missing from the
  lobby, and a lobby whose match was played is not retried: staff confirm the winner instead,
  or replay the match on purpose. A match abandoned after it started can always get a new lobby.
  The API is under `/api/games/<id>/lobby/`.
- A lobby's provisional result is shown in the match dialog and highlights the matching winner
  button without submitting it. Bracket nodes show a ringed dot for the lobby state: amber while
  it waits for players, pulsing green during the match, red when it needs attention.
- Tournament settings for hosted lobbies (mode, match start, region) and the "Send lobby info"
  Discord toggle in the tournament edit dialog. The tournament API exposes the lobby fields.
