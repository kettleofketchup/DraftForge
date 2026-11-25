- Lobby info DMs now get one ledger row per recipient (without the message body), and
  tournament DMs are no longer written to the Discord message log.
- Backend: `discordbot.utils.sync_send_dm` was replaced by `discordbot.dm.send_dm`,
  and gateway DMs go through `discordbot.gateway_dm.send_interaction_dm`. A guard test
  fails on any other DM send path.
- Test stacks with an empty `TEST_DISCORD_USER_ID` now skip every DM instead of
  sending to everyone.
