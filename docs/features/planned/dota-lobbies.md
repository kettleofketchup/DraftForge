# Dota 2 Custom Lobbies

Automated Dota 2 custom lobby creation during tournament drafts, allowing captains and spectators to seamlessly transition from drafting to in-game setup.

!!! info "GitHub Issue"
    [#56 - Lobby Handling With Tournament Game](https://github.com/kettleofketchup/DraftForge/issues/56)

## Overview

This feature integrates the `dota_lobby` service to generate and manage Dota 2 custom lobbies using league-defined rules, passwords, and settings. Lobbies are created **in parallel with drafting**, not after it.


## Implementation status

The work lands in stages. The first stage is in place and changes no behaviour:

- **`lobby` app** (`backend/lobby/`): the `GameLobby` and `GameLobbyEvent` models, and
  `DotaLobbyClient`, a client for the dota_lobby `/v1` API.
- **Tournament fields**, all off by default:
    - `dota_lobby_mode`: `off`, `manual` or `auto`
    - `dota_lobby_launch`: `manual` or `auto`
    - `dota_lobby_region`
    - `discord_send_lobby_info`
- **`Game.gameid`** is now a 64-bit field, the size of a Steam match ID.

Still to come: lobby creation, the webhook receiver, the reconcile task, and the organizer UI.

### Design notes

- **One `GameLobby` row per dota_lobby lobby.** A game keeps its lobby history, and at most one
  of its lobbies is active at a time.
- **Lobby reference:** each lobby is named `<DOTA_LOBBY_REF_PREFIX>:<game id>` in dota_lobby,
  for example `game:42`. A staging and a production DraftForge can share one dota_lobby if
  they use different prefixes.
- **Passwords are never stored.** `lobby.passwords.derive_password` computes them from the
  Django secret key and the lobby row, so a retried create sends the same request.
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
| `DOTA_LOBBY_TIMEOUT_SECONDS` | env | `15` | Per-request timeout. It is above dota_lobby's 12-second game coordinator timeout |
| `DOTA_LOBBY_REF_PREFIX` | env | `game` | Lobby reference prefix |
| `DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS` | env | `300` | Clock skew allowed on webhook timestamps |
| `DOTA_LOBBY_REGION` | env | empty | Default region name. A tournament's `dota_lobby_region` overrides it |

The backend and the Celery settings both read these variables through
`backend/config/dota_lobby.py`.

On Helm, `ingress.blockInternalApi` blocks `/api/internal/` at the ingress. dota_lobby will
therefore have to deliver webhooks to the backend Service from inside the cluster.

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
