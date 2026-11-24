Add `<SITE_URL>/api/discord/install/callback/` (for production
`https://dota.kettle.sh/api/discord/install/callback/`) to the bot application's
OAuth2 redirect URIs in the Discord Developer Portal. Without it Discord rejects the
"Connect Discord server" flow with an invalid redirect URI error.
