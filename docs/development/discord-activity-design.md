# Discord draft Activity: design and implementation plan

Issue: [#452](https://github.com/kettleofketchup/DraftForge/issues/452).
Scope includes hero drafts and team drafts, with a local server/channel pilot.

## Design decisions

Reuse the existing HeroDraftModal and DraftModal, draft functions, WebSocket
consumers and timer drivers. A second drafting engine would diverge from the
website and make permissions and reconnect behavior harder to maintain.

Persist two distinct mappings: an operator-managed voice channel points to a
hero or team draft; a verified Activity instance pins that destination at its
first connection. Multiple channels can point to one match, while other
channels point to independent matches. Moving a channel to the next match
must not redirect an already-running Activity. Database constraints require
exactly one draft kind for each mapping.

We considered choosing the latest match for a captain or trusting a draft ID
in the Activity URL. Both are ambiguous when several matches run concurrently.
Explicit channel bindings make a local pilot predictable and inspectable in
Django admin. Match selection comes from Discord's server-verified instance
location, never iframe-supplied channel IDs.

Discord OAuth authenticates an existing linked DraftForge account. The backend
checks the user participates in the instance using Discord's Activity Instance
API. A signed, twelve-hour draft credential then authenticates existing REST
actions and the dedicated Activity WebSocket. View-level captain/staff checks
remain authoritative; a spectator's credential does not confer captain powers.
Credentials stay in memory. WebSockets carry them as subprotocol offers rather
than URLs, avoiding access-log and telemetry URL exposure. The server does not
select or echo the credential subprotocol.

Website cookies remain available for normal website traffic. Activity requests
use explicit authentication before session authentication, avoiding dependence
on third-party cookies or CSRF cookies in Discord's iframe.

The Components V2 launch message uses a real interaction button; HTTP and gateway
handlers respond with LAUNCH_ACTIVITY. A user must launch the app. The bot does
not move users, join voice, or auto-launch into arbitrary channels.

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
