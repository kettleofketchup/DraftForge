Apply the new discordbot migration before enabling Activities. Configure the
Discord Developer Portal URL mappings, `VITE_DISCORD_CLIENT_ID` and backend/bot
`DISCORD_ACTIVITY_ENABLED=true`, then bind test voice channels with
`configure_draft_activity`. Activities are disabled by default. See
[local setup](docs/development/discord-activities.md) for the pilot checklist.
