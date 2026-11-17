# Discord draft Activity: design and implementation plan

Issue: [#452](https://github.com/kettleofketchup/DraftForge/issues/452).
Scope includes hero drafts and team drafts, with a local server/channel pilot.

## Design decisions

Discord's root URL launch preserves the SDK query parameters when routing to
`/activity`; regular root visits keep the website homepage. The public app ID
comes from backend runtime configuration rather than Vite build-time variables.

Reuse the existing HeroDraftModal and DraftModal, draft functions, WebSocket
consumers and timer drivers. A second drafting engine would diverge from the
website and make permissions and reconnect behavior harder to maintain.

Persist two distinct mappings. A voice channel record holds the draft last
launched or configured for that channel. A verified Activity instance records
the draft it was first opened for; that column is never rewritten and decides
the instance's tournament. Multiple channels can point to one match, while
other channels point to independent matches. Database constraints require
exactly one draft kind for each mapping.

A launch never moves or closes anyone else's view. In production, spectators
lingered in a lobby channel after the team draft, and the first hero draft
launch from that lobby rebound the channel and pulled everyone into one match.
Refusing launches while an Activity had participants was rejected too: teams
sit in locked voice channels and spectators stay. Instead the credential covers
the instance's whole tournament and every participant switches their own view
inside `/activity` (team draft, hero drafts live or finished within three
hours, bracket), or opens it in the browser. A launch updates the channel
record (refused with `channel_busy` only when that record holds an unfinished
draft from another tournament) and stores a five-minute per-user launch intent
in Redis. Reads only peek the intent; the client consumes it through the views
endpoint once it has acted on it, so the launcher, and only the launcher,
follows their launch. Initial view order: launch intent, the one live draft
the user plays in, the channel record's draft, the instance's first draft.

We considered choosing the latest match for a captain or trusting a draft ID
in the Activity URL. Both are ambiguous when several matches run concurrently.
Explicit channel bindings make a local pilot predictable and inspectable in
Django admin. Match selection comes from Discord's server-verified instance
location, never iframe-supplied channel IDs.

Discord OAuth authenticates an existing linked DraftForge account. The backend
checks the user participates in the instance using Discord's Activity Instance
API. A signed, twelve-hour credential (salt `discord-draft-activity-v3`) bound
to the user, the instance record and the tournament read at issue time then
authenticates an explicit REST allowlist and the dedicated Activity WebSocket.
Each check is "identity valid and draft in that tournament", read with
`.nocache()`. A tournament-less instance gets a credential pinned to its single
draft. View-level captain/staff checks remain authoritative; a spectator's
credential does not confer captain powers, and staff-only `reset`/`abandon` are
outside the allowlist.
Credentials stay in memory. WebSockets carry them as subprotocol offers rather
than URLs, avoiding access-log and telemetry URL exposure. The server echoes
only the `draftactivity` marker, never the credential: browsers fail a handshake
that offered subprotocols and received none. Rejected credentials are accepted
and then closed so the client can tell them apart from network errors: 4403
when the draft left the credential's tournament (no refresh; the client shows
the bracket), 4401 for everything else, including the feature flag being off,
because 0.14.x bundles know only 4401. REST failures answer 401 with
`WWW-Authenticate: DraftActivity` and a `code` (`activity_session_ended`,
`activity_out_of_scope`, `activity_path_not_allowed`, `activity_disabled`).
The client refreshes at most once per socket per credential and is
rate-limited overall, so a broken credential cannot cause a refresh storm.

v2 credentials from 0.14.x frames are accepted for one release as a pin to the
draft they show, and legacy handshakes (no `mode`) always get the instance's
first draft, so a deploy moves no open frame. Remove `LEGACY_SALT` in the next
release. Rollback order: flag off, roll back the images, flag on.

Per-user telemetry joins on `user_id` + `instance_id`: `activity_session_started`,
`activity_session_refreshed`, `activity_view_changed`, `activity_notice_seen`,
`activity_intent_declined`, `activity_open_external`, `activity_auth_rejected`
and `activity_socket_closed`. `activity_view_changed` is client-reported; the
`ws_connected` `activity.*` fields and `request_completed` `user.id` corroborate
it. Details are in [the operator guide](discord-activities.md).

Website cookies remain available for normal website traffic. Activity requests
use explicit authentication before session authentication, avoiding dependence
on third-party cookies or CSRF cookies in Discord's iframe.

The generic Components V2 message uses a real interaction button in a configured
voice channel's chat; HTTP and gateway handlers respond with LAUNCH_ACTIVITY.
Hero/team draft notifications carry an explicit kind/draft ID. Because a DM's
native callback cannot choose another channel, its button resolves the user's
current voice channel server-side and returns a short-lived embedded-app invite.
The user accepts the invite to launch or join the app there. This flow verifies
draft membership before updating the channel record and never touches existing
instances, so a stale notification cannot redirect a running match.
The bot does not move users, join voice, or auto-launch into arbitrary channels.

## Implementation sequence

1. Inspect existing draft UI, REST permissions, WebSockets and Discord routing.
2. Add persistent channel/instance bindings and a migration, admin registration,
   and an operator command that binds an existing draft and prints a launch payload.
3. Implement verified OAuth/instance resolution and draft-scoped REST/socket auth.
4. Add a client-only SDK adapter and `/activity` route; mount the existing draft
   UI after identity and destination resolve. Extend WebSocketManager to accept
   subprotocol offers while retaining ordinary website URLs.
5. Validate four channels/two matches, both draft kinds, pinned reconnects,
   malformed/expired credentials, account linking, spectators and launch callbacks.
6. Document the local tunnel, proxy mappings, settings and manual Discord pilot.
7. Check formatting, types, migrations and regressions; push the feature branch,
   open a PR, request Copilot and inspect CI using the local PR lifecycle skill.

## Pilot acceptance

Two captains launch from separate channels bound to the same hero draft. They
see the same picks, bans and clock. A teammate can watch but cannot ready or pick
as captain. Another two channels use a second match without cross-talk. Closing
and reopening an Activity resolves the persisted draft. Repeat for a team draft:
ready, player selection, clocks, pause/resume and live updates use existing code.
Finally verify a website captain can draft alongside an Activity captain.

Automated tests use mocked Discord identity/instance responses. Developer Portal
configuration and a real Discord client are required for the final live pilot;
passing mocked tests alone is not a claim that the live pilot was performed.
