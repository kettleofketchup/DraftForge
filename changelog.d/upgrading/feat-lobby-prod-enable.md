If production's `backend/.env` has no `DJANGO_SECRET_KEY`, the first `just dev::release` after
this upgrade generates one. Sessions and other values signed with the old development key
stop working, so everyone has to log in again once. Back up `backend/.env` afterwards: losing
the key ends every session again.

Lobbies are enabled on the release stack. Before deploying, put `DOTA_LOBBY_URL`,
`DOTA_LOBBY_API_KEY` and `DOTA_LOBBY_WEBHOOK_SECRET` in `backend/.env`, and set
`INTERNAL_SERVICE_ALLOWED_IPS` to the private ranges plus dota_lobby's public address
(`127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,<address>`) when dota_lobby is not on
a private network. See `docs/features/planned/dota-lobbies.md`.
