Run the migration `discordbot.0011_discordtournamentlog_lobby_info` (adds the `lobby_info` Discord log type; no data change).

Celery beat has a new entry, `reconcile-dota-lobbies` (every 60 s, in both `config/celery.py` and `config/celery_light.py`). It does nothing until `DOTA_LOBBY_ENABLED=true`.

To receive dota_lobby's webhooks, configure dota_lobby with a webhook for `https://<draftforge>/api/internal/lobbies/events/` with `token_header: X-Internal-Token`, give it DraftForge's `INTERNAL_SERVICE_TOKEN` as that URL's token and the same signing secret as `DOTA_LOBBY_WEBHOOK_SECRET`, and add the dota_lobby host to `INTERNAL_SERVICE_ALLOWED_IPS` when it is not on a private network. While the secret is empty the receiver answers `503` and dota_lobby keeps retrying. On Helm, `ingress.blockInternalApi` blocks this path at the ingress: deliver to the backend Service inside the cluster or add an ingress exception. See `docs/features/planned/dota-lobbies.md`.
