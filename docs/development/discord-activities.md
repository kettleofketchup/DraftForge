# Local Discord Activities for hero and team drafts

DraftForge exposes `/activity` through the existing React application. Both
captains and spectators must have a linked Discord account on DraftForge.
Captains retain the same permissions as on the website. Create the tournament
and draft through the existing website workflow before configuring a channel.

## Configure a local pilot

1. Use a development Discord application/bot and test server. Enable Activities
   in the Developer Portal, invite the bot, and enable the desired desktop/web
   platforms. Set the Activity entry point to `/activity`.
2. Run the local stack using `just dev::debug`. Expose its nginx HTTPS endpoint
   using an HTTPS tunnel. Use the port for your actual stack; do not assume a
   test worktree uses port 443.
3. Configure a root `/` Activity URL Mapping to the tunnel host, preserving paths.
   That one mapping must reach frontend assets, `/api/` REST and `/api/discord/activity/`
   WebSockets on the same origin. Do not map the root directly to `/activity`,
   because that would rewrite API/asset paths. Keep the entry point separate.
4. Set `VITE_DISCORD_CLIENT_ID` in the frontend build/dev environment. Set
   `DISCORD_ACTIVITY_ENABLED=true` in the backend and gateway bot environment;
   keep it false elsewhere until the pilot passes. The backend also needs
   `client_id`, `discord_secret`, `DISCORD_BOT_TOKEN` for the **same application**.
   The client secret and bot token must never be frontend variables.
5. Set `EXTRA_ALLOWED_HOSTS` to include the exact tunnel host and
   `<client-id>.discordsays.com` as required by your proxy's Host/Origin headers.
   This also permits the Activity origin through Channels' existing origin
   validator. Allow the tunnel host through Vite's dev `allowedHosts` for a dev
   server, or use a built frontend. Do not disable origin validation globally.
6. Apply migrations with `just db::migrate::dev`. Bind each **voice** channel
   using the new command (run through `just py::manage` or the stack's backend):

   ```sh
   just py::manage configure_draft_activity GUILD_ID CHANNEL_A hero HERO_DRAFT_ID
   just py::manage configure_draft_activity GUILD_ID CHANNEL_B hero HERO_DRAFT_ID
   just py::manage configure_draft_activity GUILD_ID CHANNEL_C hero OTHER_HERO_DRAFT_ID
   just py::manage configure_draft_activity GUILD_ID CHANNEL_D hero OTHER_HERO_DRAFT_ID
   # Or bind a voice channel to an existing player/team draft:
   just py::manage configure_draft_activity GUILD_ID CHANNEL_A team TEAM_DRAFT_ID
   ```

   Bindings can also be managed under Draft Activity Channels in Django admin.
   Each channel selects exactly one draft kind. Existing Activity instances
   remain attached to their original draft when a channel binding changes;
   start a new instance for a new match.
7. The command prints a Components V2 JSON payload and sends no Discord messages.
   Post that payload as the **application bot** to each configured voice
   channel's text chat using Discord's Create Message endpoint. Users join their configured voice channel and click
   **Launch Draft** in that channel. Discord chooses the launch context; the
   backend resolves the destination from the verified Activity instance's
   channel. A button cannot target an arbitrary different voice channel.
8. Use gateway interactions with the existing bot, or configure the signed HTTP
   endpoint `/api/discord/interactions/` and `DISCORD_PUBLIC_KEY`. Both launch
   handlers support callback type 12; choose one delivery mechanism per app.

## Verify

Use the acceptance checklist in [the design plan](discord-activity-design.md).
Check two matches/four channels, reconnect, captain/spectator roles, team draft
player picks, and mixed website/Activity participants. No new timer or draft
state lives in Discord. The existing database and WebSocket broadcasts are
shared across clients.

Activity credentials expire after twelve hours; reopen the Activity to obtain
fresh credentials. The first implementation does not automatically renew an
open session. Delete an instance mapping to revoke its credentials; disable
`DISCORD_ACTIVITY_ENABLED` to reject new sessions and subsequent authenticated
REST/socket handshakes. Existing open sockets close when the Activity closes.

## References

- [Activity multiplayer and instance verification](https://docs.discord.com/developers/activities/development-guides/multiplayer-experience)
- [Networking and URL mappings](https://docs.discord.com/developers/activities/development-guides/networking)
- [Embedded App SDK](https://github.com/discord/embedded-app-sdk)
- [LAUNCH_ACTIVITY interaction callback](https://docs.discord.com/developers/interactions/receiving-and-responding)
