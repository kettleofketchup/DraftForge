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
   Each channel selects exactly one draft kind. The channel record means "the
   draft last launched or configured for this channel". It seeds the first
   draft of a new Activity instance and the default view for people who join
   without a launch of their own. Changing it never moves a running instance.
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

A launch updates the channel record and stores a **launch intent** for the
clicker; it never moves or closes an Activity anyone else is watching. The
channel record is only refused when it holds an unfinished draft from another
tournament (or from no tournament): the launch replies `channel_busy`, names
that draft, links the clicker's own draft and suggests another voice channel.
No intent is stored for a refused launch. Multiple channels can share the same
hero or team draft. Finished drafts cannot be launched from a DM; reach them
through the switcher or the browser.

A launch intent lives in Redis for five minutes (the invite's lifetime), keyed
by the clicker's Discord user; the last launch wins. It only applies to an
Activity in the same guild and voice channel. The session handshake and the
drafts list **peek** it and never delete it, so a dropped response or a
credential refresh cannot lose a launch. The client consumes it by reporting
the switch (or the notice, or a captain's "Stay") to the views endpoint, which
deletes the intent only if its `intent_id` still matches. A Redis failure logs
`activity_intent_redis_failed` and the launch still succeeds; the session falls
back to the channel record.

Every notification launch logs `activity_launch_resolved`
(`system=discord`, `subsystem=activity`) with the user, draft, tournament,
resolved voice channel, outcome (`invite_created`, `no_voice`, `conflict`,
`channel_busy`, ...), the draft the channel previously held
(`previous_channel_draft`) and whether an intent was recorded
(`intent_recorded`). `channel_busy` adds `busy_draft_id` and
`busy_tournament_id`.

The generic Components V2 **Launch Draft** message is for a configured voice
channel's own chat; it retains the native type-12 callback. Notification DMs use
the voice-specific invite workflow instead.

## Inside the Activity

An Activity instance belongs to one tournament: the tournament of the draft it
was first opened for. Its credential covers every team and hero draft in that
tournament, so each person can switch views without a new handshake. The header
menu lists the tournament's team draft, every hero draft that is live or
finished within the last three hours, and the bracket. **Open in browser**
opens the current view on the website through the SDK's `openExternalLink`.
Switching only changes your own view. Captain and staff checks stay in the
existing draft views: a spectator's credential confers no captain powers on any
draft. A captain leaving their own live hero draft is asked to confirm first.

Which view you see first (`mode: "first"` handshake):

1. your launch intent for this channel, if its draft is in the tournament;
2. the one live draft you play in, if there is exactly one;
3. the channel record's draft, if it is in the tournament;
4. the instance's first draft.

A launch intent or channel record pointing at another tournament's draft shows
a notice with **Open in browser** instead. If you are already inside the
Activity when you launch, the next drafts poll (every 30 s, on menu open, and
when the frame regains focus) switches only your view.

A channel configured for a draft without a tournament gets a credential pinned
to that single draft (`scope: "draft"`) and no menu.

### Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/discord/activity/session/` | OAuth + instance check, issues the credential. Body `mode`: `first`, `refresh` (with `current_view` and the frame's `scope`; a `draft` scope stays pinned to its draft), or absent (0.14.x bundles, treated as legacy). The legacy `draft_id`/`kind` fields are always the instance's first draft. |
| `GET /api/discord/activity/drafts/` | Menu contents: tournament, team draft, hero drafts with `status`, `involves_me` and `role`, plus any applicable `launch_intent` or `notice` and `site_url`. |
| `POST /api/discord/activity/views/` | Fire-and-forget telemetry: `view`, `notice_seen`, `intent_declined`, `open_external`. Consumes intents by `intent_id`. Returns 204; throttled to 60 requests a minute per user. |

The two new endpoints accept only the Activity credential and send
`Cache-Control: no-store`.

### Credentials and failure codes

Credentials are signed with salt `discord-draft-activity-v3`, carry the user,
the instance and the tournament (or a single-draft pin), and expire after
twelve hours. They stay in memory; sockets send them as a subprotocol offer.
Every check is "identity still valid and draft still in the tournament", read
with `.nocache()` so a game removed from the tournament loses access at once.

Activity credential failures answer REST with 401, `WWW-Authenticate:
DraftActivity` and a `code` beside `detail`. Anonymous website requests are
unchanged (403).

| `code` | Cause | Socket close | Client |
| --- | --- | --- | --- |
| `activity_session_ended` | expired, bad signature, instance gone, pin mismatch, inactive user | 4401 | refreshes once, then asks to reopen |
| `activity_out_of_scope` | draft not in the credential's tournament | **4403** | goes to the bracket; no refresh |
| `activity_path_not_allowed` | endpoint outside the Activity allowlist | n/a | terminal for that call |
| `activity_disabled` | `DISCORD_ACTIVITY_ENABLED` off | 4401 | refreshes once, reads config, shows "Activities are turned off." |

Only out-of-scope closes 4403; everything else closes 4401 because 0.14.x
bundles know no other code. The client refreshes at most once per socket per
credential, at most once every 30 s and three times in ten minutes, then stops.
Open sockets revalidate every 30 s and close at credential expiry. A launch in
the same channel never closes a socket. Delete an instance mapping to revoke
its credentials.

The REST allowlist is `/api/current_user`, the hero draft endpoints the
embedded UI calls (`set-ready`, `trigger-roll`, `submit-choice`, `submit-pick`,
`list-events`, `list-available-heroes`, `pause`, `resume` and the bare draft),
the team draft `ready`/`start`/`pause`/`resume`, `pick_player`, `undo-pick`,
`get-style-mmrs`, and the two endpoints above. `reset` and `abandon` are never
reachable with an Activity credential.

### Following one person

Join a person's path (team draft, then game 1, then game 2) on `user_id` +
`instance_id`. Every event below is `system=discord`, `subsystem=activity` and
carries `user_id`, `discord_user_id`, `instance_id`, `guild_id`, `channel_id`
and `tournament_id`. Tokens, OAuth codes and `access_token` are never logged.

| Event | Logged when |
| --- | --- |
| `activity_launch_resolved` | a notification launch resolves (see above) |
| `activity_session_started` | a `first` or legacy handshake: `mode`, `scope`, `initial_kind`, `initial_draft_id`, `source` (`launch_intent`, `involves_me`, `channel_last`, `instance_first`, or `legacy` for the instance's first draft that a 0.14.x bundle shows), `role`, `notice`, `intent_id` |
| `activity_session_refreshed` | a `refresh` handshake: the client-reported `current_kind`/`current_id` |
| `activity_view_changed` | a view switch: `from_*` (client-claimed), `to_*`, `trigger`, `role`, `intent_id`, `intent_consumed` |
| `activity_notice_seen` | a cross-tournament notice was shown |
| `activity_intent_declined` | a captain pressed Stay instead of following their launch; the intent is consumed so later polls do not ask again |
| `activity_open_external` | **Open in browser**, with the server-derived `path` |
| `activity_auth_rejected` | a credential failure: `surface`, `reason`, `code` |
| `activity_socket_closed` | an Activity socket closes: `close_code`, `reason`, `role`, `duration_s` |
| `activity_intent_redis_failed` | a Redis error while recording, peeking or consuming an intent |

`activity_view_changed` is reported by the client. Corroborate it with the
server's own records for the target draft: `ws_connected` with the
`activity.instance_id`, `activity.kind` and `activity.role` fields, and
`request_completed` with `user.id`.

## Deploying

Open 0.14.x frames keep working after the deploy: their v2 credentials
(salt `discord-draft-activity-v2`) are accepted for this release as a pin to
the draft they already show, and a later refresh from an old bundle returns the
instance's first draft, so they stay where they are. They get no switcher until
reopened. Follow-up: remove `LEGACY_SALT` and the v2 grace in the next release.
Nothing breaks during an event, but prefer deploying between events.

## Rolling back

To turn Activities off, set `DISCORD_ACTIVITY_ENABLED` off. Every open frame,
old or new bundle, gets one 4401, refreshes once and shows "Activities are
turned off." without looping.

To roll back the images, first turn the flag off, then roll back the images,
then turn the flag back on. That way no new-bundle frame meets the old backend
mid-session. A new bundle that does meet an old backend treats a session
response without `scope` as a single-draft credential.

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

Also check that a second match launched into a shared lobby channel moves
nobody else, that each person can switch between the team draft, hero drafts
and bracket, and that a game removed from the tournament closes its socket with
4403 and lands the viewer on the bracket. Credential and close-code behavior is
under [Credentials and failure codes](#credentials-and-failure-codes).

## References

- [Activity multiplayer and instance verification](https://docs.discord.com/developers/activities/development-guides/multiplayer-experience)
- [Networking and URL mappings](https://docs.discord.com/developers/activities/development-guides/networking)
- [Embedded App SDK](https://github.com/discord/embedded-app-sdk)
- [Create a voice-channel Activity invite](https://docs.discord.com/developers/resources/channel#create-channel-invite)
- [Read a user's current voice state](https://docs.discord.com/developers/resources/voice#get-user-voice-state)
- [LAUNCH_ACTIVITY interaction callback](https://docs.discord.com/developers/interactions/receiving-and-responding)
