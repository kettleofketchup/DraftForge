# Local Discord Activities for hero and team drafts

DraftForge exposes `/activity` through the existing React application. Both
captains and spectators must have a linked Discord account on DraftForge.
Captains retain the same permissions as on the website. Create the tournament
and draft through the existing website workflow before launching an Activity.

## Configure a local pilot

1. Use a development Discord application/bot and test server. Enable Activities
   in the Developer Portal, invite the bot, and enable the desired desktop/web
   platforms. Discord opens the root URL; DraftForge detects the Activity query
   parameters and routes to `/activity` while preserving them. For an app still
   in development, the pilot participants must be application developers/team
   members; inviting the bot to a server alone does not grant Activity access.
2. Run the local stack using `just dev::debug`. Expose its nginx HTTPS endpoint
   using an HTTPS tunnel. Use the port for your actual stack; do not assume a
   test worktree uses port 443.
3. Configure a root `/` Activity URL Mapping to the tunnel host, preserving paths.
   That one mapping must reach frontend assets, `/api/` REST and `/api/discord/activity/`
   WebSockets on the same origin. Do not map the root directly to `/activity`,
   because that would rewrite API/asset paths. The app handles its own Activity
   entry route; no separate Portal path setting is needed.
4. Set `DISCORD_ACTIVITY_ENABLED=true` in the backend, Celery worker and gateway
   bot environment;
   keep it false elsewhere until the pilot passes. The backend also needs
   `client_id`, `discord_secret`, `DISCORD_BOT_TOKEN` for the **same application**.
   The public client ID is loaded at runtime from
   `/api/discord/activity/config/`, so existing frontend images can be used.
   The client secret and bot token must never be frontend variables.
5. Set `EXTRA_ALLOWED_HOSTS` to include the exact tunnel host and
   `<client-id>.discordsays.com` as required by your proxy's Host/Origin headers.
   This also permits the Activity origin through Channels' existing origin
   validator. Allow the tunnel host through Vite's dev `allowedHosts` for a dev
   server, or use a built frontend. Do not disable origin validation globally.
6. Apply migrations with `just db::migrate::dev`. Notification launch buttons
   bind an unassigned voice channel automatically after verifying the user
   belongs to the draft. For a manual pilot or an explicit channel assignment,
   run the command with the **same development environment** as the stack:

   ```sh
   ./scripts/in-env.sh dev backend ../.venv/bin/python manage.py configure_draft_activity GUILD_ID CHANNEL_A hero HERO_DRAFT_ID
   ./scripts/in-env.sh dev backend ../.venv/bin/python manage.py configure_draft_activity GUILD_ID CHANNEL_B hero HERO_DRAFT_ID
   ./scripts/in-env.sh dev backend ../.venv/bin/python manage.py configure_draft_activity GUILD_ID CHANNEL_C hero OTHER_HERO_DRAFT_ID
   ./scripts/in-env.sh dev backend ../.venv/bin/python manage.py configure_draft_activity GUILD_ID CHANNEL_D hero OTHER_HERO_DRAFT_ID
   # Or bind a voice channel to an existing player/team draft:
   ./scripts/in-env.sh dev backend ../.venv/bin/python manage.py configure_draft_activity GUILD_ID CHANNEL_A team TEAM_DRAFT_ID
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
8. Use gateway interactions with the existing bot (discord.py 2.6 or later), or
   configure the signed HTTP endpoint `/api/discord/interactions/` and
   `DISCORD_PUBLIC_KEY`. Choose one delivery mechanism per app. Signed HTTP
   notification launches require the Celery worker to finish the deferred reply.
9. Add the external image mappings listed below so hero portraits and avatars
   load through Discord's proxy.

## Draft notification buttons

When Activities are enabled, hero and team draft DMs contain **Launch / Join
Activity** beside **Open in Browser**. Join your team's voice channel in the
associated tournament server, then click the notification button. DraftForge
checks your linked account and draft membership, reads your current voice
channel from Discord, and returns a five-minute Activity invite. Open that
invite to launch DraftForge or join the instance already running in that channel.

Discord requires accepting this invite: a DM's `LAUNCH_ACTIVITY` callback cannot
choose a different voice channel. No Activity opens automatically and the bot
never joins voice. The bot needs View Channel, Connect and Create Invite
permissions in the destination channel. Joining another voice channel after an
invite is generated does not retarget it; click the original notification again.

An assigned channel cannot be silently taken over by another draft, including a
completed draft's old binding. Finish/close the old Activity, then have an
organizer explicitly reconfigure the channel for the next match. Multiple
channels can share the same hero or team draft. An existing Activity remains
pinned to its original draft until it is closed and a new instance is started.

The generic Components V2 **Launch Draft** message is for a configured voice
channel's own chat; it retains the native type-12 callback. Notification DMs use
the voice-specific invite workflow instead.

## External image mappings

Add these URL mappings alongside the root application mapping in the Developer
Portal. Prefixes must match exactly; preserve the remainder of each image path.
The Activity SDK rewrites image `src` attributes only inside the Activity.
Website requests and draft WebSocket URLs retain their normal behavior.

| Prefix | Target |
| --- | --- |
| `/external/steam` | `cdn.cloudflare.steamstatic.com` |
| `/external/discord` | `cdn.discordapp.com` |
| `/external/avatars` | `ui-avatars.com` |

Without these mappings Discord's proxy policy blocks hero portraits and avatars,
even if the same absolute URLs load in an ordinary browser.

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
REST/socket handshakes. Open Activity sockets also revalidate their credentials
periodically and close at credential expiry or after revocation is detected.

## References

- [Activity multiplayer and instance verification](https://docs.discord.com/developers/activities/development-guides/multiplayer-experience)
- [Networking and URL mappings](https://docs.discord.com/developers/activities/development-guides/networking)
- [Embedded App SDK](https://github.com/discord/embedded-app-sdk)
- [Create a voice-channel Activity invite](https://docs.discord.com/developers/resources/channel#create-channel-invite)
- [Read a user's current voice state](https://docs.discord.com/developers/resources/voice#get-user-voice-state)
- [LAUNCH_ACTIVITY interaction callback](https://docs.discord.com/developers/interactions/receiving-and-responding)
