# Dota 2 Custom Lobbies

Automated Dota 2 custom lobby creation during tournament drafts, allowing captains and spectators to seamlessly transition from drafting to in-game setup.

!!! info "GitHub Issue"
    [#56 - Lobby Handling With Tournament Game](https://github.com/kettleofketchup/DraftForge/issues/56)

## Overview

This feature integrates the `dota_lobby` service to generate and manage Dota 2 custom lobbies using league-defined rules, passwords, and settings. Lobbies are created **in parallel with drafting**, not after it.


## Implementation status

The work lands in stages. The first stage added the data model and client and changed no
behaviour:

- **`lobby` app** (`backend/lobby/`): the `GameLobby` and `GameLobbyEvent` models, and
  `DotaLobbyClient`, a client for the dota_lobby `/v1` API.
- **Tournament fields**, all off by default:
    - `dota_lobby_mode`: `off`, `manual` or `auto`
    - `dota_lobby_launch`: `manual` or `auto`
    - `dota_lobby_region`
    - `discord_send_lobby_info`
- **`Game.gameid`** is now a 64-bit field, the size of a Steam match ID.

The second stage creates and follows lobbies (see [Lobby lifecycle](#lobby-lifecycle)): automatic
and manual creation, the webhook receiver, the reconcile task, game updates, live updates on the
tournament websocket and the opt-in Discord message.

The third stage adds the organizer and player API and the UI (see
[Organizer API and UI](#organizer-api-and-ui)): lobby state, password and invites in the match
dialog, staff controls to create, retry, invite, launch and close, the provisional result next
to the winner buttons, a lobby dot on bracket nodes, and the tournament settings.

### Lobby lifecycle

**When a game gets a lobby.** Both `DOTA_LOBBY_ENABLED` and the tournament's `dota_lobby_mode`
must allow it. In `auto` mode a game gets a lobby once all of these hold:

- the tournament is `in_progress`, is a Dota 2 tournament, and its game mode is Normal,
  Captain's Mode or Turbo (`ap`, `cm`, `turbo`). "Custom Lobby" is refused: dota_lobby cannot
  host custom games;
- the game is `pending` and has both teams;
- every rostered player (members and captain) has a Steam account ID, and no side has more
  than five.

The trigger is the game's save (a `post_save` signal, sent on commit). The reconcile task also
sweeps for eligible games every minute, so a missed signal or a tournament that just started is
picked up. In `manual` mode, and for retries, staff use the match dialog (see
[Organizer API and UI](#organizer-api-and-ui)), the Django admin action "Create a new lobby for
these games" on a game's lobby, or `python manage.py create_dota_lobby <game id>
[--allow-missing] [--replay]`. `--allow-missing` leaves players without a Steam account out of
the roster; automatic creation never does.

A lobby that times out or fails is not recreated automatically: organizers retry it. A lobby
whose match finished with a result is not retried for the same two teams
(`lobby_match_played`): the organizer confirms the winner instead. To host that match again,
for example after resetting a disputed game to pending, organizers ask for a replay (`replay`
on the create request, "Replay match" in the dialog, or `--replay`); automatic creation never
replays a match. A match that ended unscored, or that started and whose lobby then ended
without a scored result, was abandoned: the game goes back to pending and may get a new lobby.

**Creating.** Celery never touches the database. The `create_dota_lobby` task:

1. claims the lobby through the internal API. Under a lock on the game, Django creates a
   `requested` row and builds the request: name `"<tournament> R<round>: <radiant> vs <dire>"`,
   teams from the bracket slots (`team-<pk>` refs, the team captain marked), the league from
   the tournament's lobby league ID or its league, the tournament's launch mode and region,
   `tv_delay_seconds: 120`, `kick_strangers: true`, and the game and row IDs as metadata. The
   row keeps the tournament's lobby password as it is at that moment (see
   [Event lobby passwords](#event-lobby-passwords)); the stored request leaves it out, and
   every send adds the row's password;
2. sends it to dota_lobby. A repeat sends the same request, so dota_lobby answers `200` with
   the existing lobby instead of `409`;
3. reports the answer back. Only errors dota_lobby marks retryable (`503`, `504`), timeouts and
   connection errors are retried. The reconcile task resends a create left `requested` only
   once no attempt is in flight: each attempt holds the row for two minutes, and a retryable
   failure holds it until the task's own retry is due plus those two minutes
   (`next_attempt_at`). Any error (`league_not_held`, `invalid_request`, ...) ends the row in
   state `error` with `last_error_code` for organizers. A `409 conflict` is resolved by
   looking up the lobby holding the reference: DraftForge adopts it when it is the same row's,
   closes it and retries when it is an earlier lobby of the same game, and gives up otherwise.

A manual create (staff, the admin action or `manage.py create_dota_lobby`) makes the
`requested` row at once, so staff can close it before the task runs. The task, and every retry
of it, carries the row's ID: once the row has ended (closed by staff or replaced), the next
claim answers `409 lobby_ended` and the task stops instead of creating a new lobby.

**Teams and sides.** When a game's teams change while its lobby has not started (`requested`
to `ready`), the lobby is ended (`closed`, reason `teams_changed`), closed in dota_lobby, and a
new one is requested for the new teams. Swapping the two teams between bracket slots is not a
change. Once a match is under way the lobby is left alone and the change is logged. Deleting a
game closes its lobby in dota_lobby, and so does completing a game (or giving it a winner,
as advance-winner does for a forfeit) while its lobby has not started (reason
`game_completed`).

The sides sent are stored on the lobby row (`radiant_team`, `dire_team`). When the hero draft
completes with the other side choice, DraftForge asks dota_lobby to flip the teams once the
lobby is `waiting` or `ready`; the `lobby.teams_flipped` event updates the stored sides.

**Events.** dota_lobby posts every event to `POST /api/internal/lobbies/events/`. The receiver:

- answers `503` while lobbies are disabled or `DOTA_LOBBY_WEBHOOK_SECRET` is empty, so
  dota_lobby keeps retrying (for up to 24 hours) instead of giving up;
- requires `X-Internal-Token` (DraftForge's internal service auth, IP allowlist included) and
  verifies `X-Dota-Lobby-Signature` over the raw body with each configured secret, allowing
  `DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS` of clock difference. A bad signature gets `401`;
- stores each event once by ID and applies a lobby's events strictly in `seq` order. Duplicates
  and old events get `200`. An event that arrives after a gap is stored, and the missing ones
  are read from dota_lobby in the background;
- answers `200` with `ignored` for a lobby that is not this DraftForge's (another
  `DOTA_LOBBY_REF_PREFIX`), so dota_lobby does not retry it.

**What changes on the game.**

| Event | Effect |
|-------|--------|
| `match.started` | A `pending` game becomes `live`. The match ID is kept on the lobby (`match_id`) only: `Game.gameid` stays empty, so the Steam auto-link still scans the game and sets its match ID and winner |
| `match.ended` with `scored: false`, or a lobby that ends (`failed`, `closed`, `timed_out`, `finished`, or unknown to dota_lobby) after its match started without a scored result | A `live` game without a winner goes back to `pending`, so organizers can request a new lobby |
| `match.ended` | Recorded on the lobby only, as a provisional result (`provisional_winner_side`, `provisional_winner_team`, outcome, duration). The winner is not set, the game is not completed and the bracket does not advance: staff confirm with advance-winner, and the Steam league sync stays the authority |
| lobby events | The lobby row's state, bot, players and sides. The state reason comes only from `lobby.state_changed` and the terminal events, not from the `reason` of a player or launch event |

Only the game's active lobby, created for the teams the game has now, changes the game. A
lobby DraftForge already ended (for example closed because the teams changed while dota_lobby
was launching it) still records its own events, but never touches the game.

**Reconcile.** `reconcile-dota-lobbies` runs every 60 seconds (in both beat schedules,
`config/celery.py` and `config/celery_light.py`). For every lobby that has not ended it reads
the lobby from dota_lobby, applies any events the webhooks missed, closes rows dota_lobby no
longer knows, resends creates left `requested` with no attempt in flight, queues pending side flips, finishes
closes dota_lobby has not confirmed, and creates lobbies for eligible games. It does nothing
while `DOTA_LOBBY_ENABLED` is off.

**Closing.** Closing a lobby (staff, a replace, changed teams, a completed game) ends the row in
DraftForge at once, so a new lobby can be requested, and closes it in dota_lobby from Celery.
The row stays `close_pending` until dota_lobby confirms the close (or answers that the lobby is
gone or already in its match). If the close task gives up, for example while dota_lobby is
restarting or `DOTA_LOBBY_ENABLED` is off, the reconcile task tries again every minute. A row
that ended before dota_lobby's answer to its create was recorded has no lobby ID: it is closed
by its reference, only the lobby whose metadata names that row, and the reconcile task keeps
looking until the create attempt's lease has run out.

**Live updates.** The tournament websocket (`/api/tournament/<id>/`) gets a `lobby_event`
message (`game_id`, `state`, `match_id`, `provisional_winner_side`; never the password) when a
lobby changes, and a `bracket_update` message when a lobby changes a game's status. The
frontend already refetches the bracket on `bracket_update`.

**Discord.** With the tournament's `discord_send_lobby_info` on, rostered players with a
linked Discord account get a DM when the lobby is created in the game: the lobby name, the
password (read from dota_lobby), their side and the region. The tournament's Discord log
records the send (`lobby_info`) without the password; no per-message log is kept for these
DMs, because it would store the embed.

### Organizer API and UI

**API.** Under `api/games/<game id>/lobby/`, next to `create-herodraft`:

| Method and path | Who | What it does |
|-----------------|-----|--------------|
| `GET .../lobby/` | Signed-in users | The game's active lobby, or its latest one. Everyone gets the state, the lobby's match ID, the sides and the provisional result. The game's rostered players (members and captains of either team) and tournament staff also get the lobby name, the password, per-player invite and seat status and the last error. Staff also get `eligibility` (whether and why not the game can get a lobby now, with the names of players missing a Steam account) |
| `POST .../lobby/` | Tournament staff | Request a lobby, or retry after one ended. `{"allow_missing": true}` leaves players without a Steam account out; `{"replace": true}` first closes an active lobby whose match has not started. Answers `202`: the create runs in Celery |
| `DELETE .../lobby/` | Tournament staff | Close the active lobby before its match starts (reason `closed_by_staff`) |
| `POST .../lobby/invite/` | Staff, or a rostered player | Staff send `{"missing": true}` or `{"players": [account_id, ...]}`. A player always invites only themselves |
| `POST .../lobby/launch/` | Tournament staff | Start the match; `{"force": true}` starts it before every player is seated and ready |

Errors are `{"error", "code"}`. Invite and launch call dota_lobby directly and pass its problem
`code`, `retryable` and status through (`409 not_ready`, `422 league_not_held`,
`429 invite_limited` with `Retry-After`, `503 unavailable`, `504 gc_timeout`); a `401` or `403`
from dota_lobby (a wrong `DOTA_LOBBY_API_KEY`) becomes `502`. Because they wait for dota_lobby
inside the web request, each user gets 12 invites and 12 launches a minute; after that the
answer is `429 rate_limited` with `Retry-After`. Connecting to dota_lobby times out after 3
seconds; `DOTA_LOBBY_TIMEOUT_SECONDS` is the read timeout. The password is the one the lobby
was created with (see [Event lobby passwords](#event-lobby-passwords)) and is never in bracket
data, websocket messages or logs. It is shown only while the lobby is active.

The bracket (`GET /api/bracket/tournaments/<id>/`) gives each game a `lobby_state`: the state
of its latest lobby, or `null`. The tournament API exposes `dota_lobby_mode`,
`dota_lobby_launch`, `dota_lobby_region` and `discord_send_lobby_info`, and the read-only
`game_mode` and `lobby_steam_league_id`. Staff edit the four lobby settings on a standalone
tournament only: a tournament created from an event takes them from the event, and a change
to them answers `400`. The tournament's password is never in the tournament API.

**UI.**

- The match dialog has a "Dota lobby" panel for signed-in users: the state, and for the game's
  players and staff the lobby name, the password with a copy button, and each player's invite
  and seat status. Players can send themselves an invite while the lobby is waiting for
  players.
- Staff get Create (or Retry, after a lobby ended), Recreate, Invite missing, Launch (a force
  confirmation unless the lobby is `ready`), Close, and a re-invite button per player. The
  last error is explained (no bot holds the league, no bot is free, players without Steam
  accounts by name, ...).
- When the lobby reports a result, the panel shows it as provisional, and the matching
  winner button is highlighted as "(lobby result)". Nothing is submitted: staff still click it.
- Bracket nodes show a coloured dot for the lobby state; lobbies that closed or finished
  normally show none.
- The tournament edit dialog has a "Dota Lobbies" section on the Config tab (off, manual or
  automatic; match start; region) and a "Send lobby info" toggle on the Discord tab. For a
  tournament created from an event they are read-only, with a link to the event.
- Series and event forms (create, edit and one-off) have the same settings for Dota 2, and a
  "Lobby password" section: see [Event lobby passwords](#event-lobby-passwords).
- The panel refreshes on the tournament websocket's `lobby_event` message. The bracket is
  refetched only when the message's state differs from the one its lobby dot shows, so
  invites, joins and ready checks do not make every viewer reload the bracket.

### Event lobby passwords

Every lobby of an event, in every tournament of the event, uses one password. Staff choose
how it is set, on the series or on the event:

- **Random** (the default): DraftForge generates a password when the event is created, or
  when the event switches to random. Generated passwords have 12 characters from
  `abcdefghjkmnpqrstuvwxyz23456789` (no `i`, `l`, `o`, `0` or `1`). In random mode the series
  stores no password: each of its events gets its own.
- **Fixed**: staff type the password ahead of time. dota_lobby accepts 1 to 32 characters; a
  fixed password must be printable ASCII without leading or trailing spaces.

**Where it lives.** The series stores the mode and, in fixed mode, the password. Each event
stores its effective password (`Event.dota_lobby_password`) and copies it, with the lobby
settings, onto its tournament (`events.services.LOBBY_CONFIG_FIELDS`). Claiming a lobby
copies the tournament's password onto the `GameLobby` row (`GameLobby.password`), so a
retried create sends the same request and dota_lobby answers it as a repeat rather than a
conflict. A standalone tournament (no event) gets a random password when its lobbies are
switched on.

**The series cascade.** Generated events inherit the series' lobby settings and password
mode. A fixed series password is copied to them; in random mode each event gets its own.
Saving the series updates its upcoming, on-schedule events, like every other series setting:
a fixed password replaces theirs, a random series keeps each event's random password and
generates one for an event that had a fixed password. Off-schedule (one-off) events and
events past `upcoming` are left alone. An event can override the series' settings until the
next series save while it is still `upcoming`.

**Changing it.** A new password (edit, regenerate or series cascade) reaches the event's
tournament unless the tournament is over, including an in-progress one. Only lobbies created
afterwards use it: lobbies that already exist keep the password they were created with. To
lock out a player who has left the event, regenerate the password and recreate the lobbies
that are still waiting.

!!! warning "One password for the whole event"
    Anyone who has the password can join any lobby of the event, not only their own match.
    Lobbies invite rostered players and kick strangers (`kick_strangers: true`), but treat the
    password as shared within the event. Per-lobby passwords, which made a recreated lobby
    unusable for players who had left the game, no longer exist.

**Who sees it.**

| Who | Where |
|-----|-------|
| Org staff of the event's organization (who can edit the event) | Series and event settings (`GET .../lobby-password/`), the event page, the match dialog |
| Registered players: an `approved` or `confirmed` signup, or a member or captain of a team in the event's tournament | The event page, ahead of time (`GET /api/events/<id>/lobby-password/`), and the match dialog for their own games |
| Everyone else (including `rsvp`, `pending_approval`, `waitlisted`, `tentative`, `rejected` and `cancelled` signups, and league staff who are not org staff) | Never: the endpoint answers `404` |

The password is write-only on the events API: it is never in event, series or tournament
payloads (which are cached and public), in the data Celery tasks read, in websocket messages,
in logs (`lobby_password_changed` logs the event, mode and reason only) or in Discord
announcements. The opt-in Discord lobby info DM still sends it to the game's rostered players.

**API.**

| Method and path | Who | What it does |
|-----------------|-----|--------------|
| `GET /api/events/<id>/lobby-password/` | Org staff, registered players | Staff get `{mode, password, source, can_manage}` (`source` is `series` while the event matches its series); registered players get `{password}`; anyone else `404` |
| `POST /api/events/<id>/lobby-password/regenerate/` | Org staff | A new random password; `409` when the event's password is fixed |
| `GET /api/events/repeaters/<id>/lobby-password/` | Org staff | `{mode, password, can_manage}`; `password` is `null` in random mode |
| `PATCH /api/events/<id>/`, `PATCH /api/events/repeaters/<id>/`, the create endpoints | Org staff | Write `dota_lobby_password_mode` and the write-only `dota_lobby_password`. Fixed mode needs a valid password (the current one is kept when none is sent); in random mode a sent password is ignored |

### Connecting dota_lobby

1. Give DraftForge and dota_lobby the same webhook secret. In dota_lobby,
   `just secrets webhook-secret https://<draftforge>/api/internal/lobbies/events/` generates
   it, and `just secrets webhook-secret-env <url> <draftforge>/backend/.env` writes it into
   DraftForge's env file as `DOTA_LOBBY_WEBHOOK_SECRET` without printing it.
2. Give dota_lobby DraftForge's `INTERNAL_SERVICE_TOKEN` for that URL
   (`just secrets webhook-token <url>`, read from stdin), and configure the webhook with
   `token_header: X-Internal-Token` and `events: ["*"]`.
3. If dota_lobby is not on a private network, allow its address in
   `INTERNAL_SERVICE_ALLOWED_IPS`. Setting that variable replaces the built-in allowlist
   (loopback and the RFC 1918 ranges) rather than adding to it, so list those too, or the
   Celery workers and the Discord bot lose the internal API:
   `127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,<dota_lobby address>`. A `403`
   makes dota_lobby give the delivery up at once; the reconcile task still catches up within
   a minute.
4. Set `DOTA_LOBBY_URL` and `DOTA_LOBBY_API_KEY`, then `DOTA_LOBBY_ENABLED=true`, and set a
   tournament's `dota_lobby_mode`.

### Design notes

- **One `GameLobby` row per dota_lobby lobby.** A game keeps its lobby history, and at most one
  of its lobbies is active at a time.
- **Lobby reference:** each lobby is named `<DOTA_LOBBY_REF_PREFIX>:<game id>` in dota_lobby,
  for example `game:42`. A staging and a production DraftForge can share one dota_lobby if
  they use different prefixes.
- **Passwords are stored, one per event.** See [Event lobby passwords](#event-lobby-passwords).
  Lobbies used to derive a password per lobby from the Django secret key; the upgrade stores
  the derived password of every lobby that had not ended, so a create retried across the
  upgrade stays identical. Rotating `DJANGO_SECRET_KEY` no longer affects lobby passwords.
  The match dialog shows the lobby's stored password; the Discord message reads it from
  dota_lobby (`get_lobby`).
- **Errors:** dota_lobby answers errors as problem+json. The client raises `DotaLobbyError` and
  callers act on its `code` and `retryable` fields, never on the message text. Only `503`
  (`unavailable`), `504` (`gc_timeout`), timeouts and connection errors are retryable.

### Configuration

| Variable | Where | Default | Purpose |
|----------|-------|---------|---------|
| `DOTA_LOBBY_ENABLED` | `docker/.env.<stack>`, Helm `env.extra` | `false` | Global switch |
| `DOTA_LOBBY_URL` | `backend/.env`, Helm `env.extra` | empty | dota_lobby base URL, without `/v1` |
| `DOTA_LOBBY_API_KEY` | `backend/.env`, Helm `secrets.dotaLobbyApiKey` | empty | Sent as `X-API-Key` |
| `DOTA_LOBBY_WEBHOOK_SECRET` | `backend/.env`, Helm `secrets.dotaLobbyWebhookSecret` | empty | The webhook signing secret dota_lobby uses for DraftForge's URL. A comma-separated list is accepted while rotating |
| `DOTA_LOBBY_TIMEOUT_SECONDS` | env | `15` | Read timeout per request (connecting is capped at 3 seconds). It is above dota_lobby's 12-second game coordinator timeout |
| `DOTA_LOBBY_REF_PREFIX` | env | `game` | Lobby reference prefix |
| `DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS` | env | `300` | Clock skew allowed on webhook timestamps |
| `DOTA_LOBBY_REGION` | env | empty | Default region name. A tournament's `dota_lobby_region` overrides it |

The backend and the Celery settings both read these variables through
`backend/config/dota_lobby.py`.

On Helm, `ingress.blockInternalApi` (on by default) blocks `/api/internal/` at the ingress, so
dota_lobby has to deliver webhooks to the backend Service from inside the cluster, or the
ingress needs an exception for `/api/internal/lobbies/events/`. Without webhooks the reconcile
task still keeps lobbies up to date, a minute behind.

---

## Goals

- Automatically create a Dota 2 custom lobby while captains are drafting
- Apply league-specific lobby rules consistently
- Reduce manual setup errors and delays before matches
- Allow admins to quickly restart or regenerate lobbies when needed

---

## Features

### Lobby Generation Integration

Utilizes the [dota_lobby](https://github.com/kettleofketchup/dota_lobby) service.

When a **draft game** is clicked:

- Trigger a bot/service to create a Dota 2 custom lobby
- Apply league-specific rules and settings
- Generate lobby credentials (name + password)

---

### Captain Invitations

- Automatically send lobby invites to Radiant and Dire captains
- Ensure captains can immediately join once the lobby is created

---

### League-Scoped Lobby Configuration

Leagues store custom lobby rules as a **YAML schema**:

- YAML should be versionable
- UI provides toggle options for different lobby value types
- Leagues store:
    - Lobby generation password(s)
    - Default lobby settings (game mode, series type, etc.)

---

### League Admin UI

League page controls for:

- View current lobby configuration
- Edit custom lobby settings (YAML editor)
- Update lobby passwords
- Validation for YAML schema before saving

---

### Lobby Lifecycle Controls

Buttons/actions for:

- Restart lobby
- Regenerate lobby (new password)
- Restarting does not break the active draft state

---

## Acceptance Criteria

- [ ] Draft page can trigger lobby creation via `dota_lobby`
- [ ] Draft page can view state of lobby and bot
- [ ] Lobby uses league-defined rules
- [ ] Captains receive invites automatically
- [ ] League admins can edit lobby settings from the UI
- [ ] Lobby can be restarted/regenerated safely
- [ ] Lobby state is visible to spectators

---

## Future Enhancements

- Auto-start lobby when draft completes
- Lobby status indicators (created / players joined / ready)
- Audit logs for lobby restarts and config changes
