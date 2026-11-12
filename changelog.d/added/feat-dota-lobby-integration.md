- Groundwork for in-game Dota 2 lobbies through the dota_lobby service (#56): a new
  `lobby` app that records each lobby a game gets and the events dota_lobby reports,
  and a client for the dota_lobby API that reads its problem+json errors and retries
  only the ones dota_lobby marks retryable. Nothing calls dota_lobby yet.
- Tournaments have dota_lobby settings (`dota_lobby_mode`, `dota_lobby_launch`,
  `dota_lobby_region`, `discord_send_lobby_info`), all off by default.
