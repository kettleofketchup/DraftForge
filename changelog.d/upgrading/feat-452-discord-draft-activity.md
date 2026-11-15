Apply the new discordbot migration before enabling Activities. Configure the
Discord Developer Portal URL mappings and backend/worker/bot
`DISCORD_ACTIVITY_ENABLED=true`, then bind test voice channels with
`configure_draft_activity`. Activities are disabled by default. See
[local setup](docs/development/discord-activities.md) for the pilot checklist.

The frontend reads the public application ID from the backend at runtime. The
bot needs voice-channel Connect and Create Invite permissions for notification
launches; signed HTTP launches also need the Celery worker running.
