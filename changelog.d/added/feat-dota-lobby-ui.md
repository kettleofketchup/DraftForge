- Organizer and player controls for dota_lobby lobbies (#56). The match dialog shows a game's
  lobby state, and to its players and tournament staff the lobby name, password and each
  player's invite and seat status. Staff can create, retry, recreate, close and launch the
  lobby and re-invite players, and players can invite themselves. The API is under
  `/api/games/<id>/lobby/`.
- A lobby's provisional result is shown in the match dialog and highlights the matching winner
  button without submitting it. Bracket nodes show a dot for the lobby state.
- Tournament settings for hosted lobbies (mode, match start, region) and the "Send lobby info"
  Discord toggle in the tournament edit dialog. The tournament API exposes the lobby fields.
