- In-game Dota 2 lobbies through the dota_lobby service (#56), for tournaments that opt in
  with `dota_lobby_mode`: a game gets a lobby automatically once both teams are set
  (`auto`), or when staff request one (`manual`; Django admin action or
  `manage.py create_dota_lobby`). Changing a game's teams before the match closes the lobby
  and requests a new one; completing a game before its lobby's match starts closes the lobby;
  and the lobby's sides follow the hero draft's side choice.
- dota_lobby events are received at `/api/internal/lobbies/events/` (signed and
  de-duplicated) and kept in step by a reconcile task every minute. A started match marks the
  game live and keeps its match ID on the lobby, leaving `Game.gameid` to the Steam link; a
  match that ends unscored, or a lobby that ends before a scored result, returns the game to
  pending so a new lobby can be requested. The lobby's reported result is kept as
  provisional for staff to confirm and never advances the bracket.
- The tournament websocket now sends `lobby_event` and `bracket_update` messages, so the
  bracket refreshes when a lobby's match starts.
- Optional Discord DM with the lobby name, password and side for rostered players
  (`discord_send_lobby_info`).
