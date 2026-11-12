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
  Django secret key and the lobby reference, so a retried create, or a lobby recreated for the
  same game, sends the same request and dota_lobby answers it as a repeat rather than a
  conflict.
  - Each lobby row records which secret key its password comes from. When rotating
    `DJANGO_SECRET_KEY`, put the old key in `DJANGO_SECRET_KEY_FALLBACKS` until the lobbies
    made under it have ended; without it their passwords can no longer be derived.
  - What players are shown should be read from dota_lobby (`get_lobby` returns the password),
    since that is the lobby they join.
  - The password is refused when `DJANGO_SECRET_KEY` is unset and the public development key
    is in use, outside `DEBUG` and tests.
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

### Where dota_lobby runs

Production DraftForge (`dota.kettle.sh`) uses the dota_lobby instance on KettleCluster, at
`https://dota-lobby.home.kettle.sh`. It is the `dota-lobby` app in `kettleofketchup/home`
(`apps/dota-lobby`), deployed by ArgoCD. The dota_lobby docs cover the setup in detail:
[Kubernetes](https://kettleofketchup.github.io/dota_lobby/deployment/kubernetes/).

- **Access:** the host is reached through the Cloudflare tunnel without Authentik
  forward-auth. Traefik allows only the DraftForge production server's address. That check
  relies on a forwarded header someone on the home LAN could forge, so the API key is the
  real gate.
- **Production settings:** `DOTA_LOBBY_URL` and `DOTA_LOBBY_API_KEY` are in
  `backend/.env` on the production host. The key's source of truth is
  `apps/dota-lobby/dota-lobby-api.enc.yaml` (sops); when rotating it, update both and
  restart the backend services. `DOTA_LOBBY_ENABLED` stays `false` in
  `docker/.env.release` until DraftForge creates lobbies.
- **Bots:** one Steam bot, `draftforge1`. Its credentials live in the dota_lobby repository
  (`secrets/bots/draftforge1.sops.yaml`) and are copied into the cluster Secret with
  `just secrets k8s-secret`. A second bot (`draftforge2`) has credentials but is not
  deployed. Each account may run in only one dota_lobby instance at a time, so do not run
  these bots locally while the cluster instance is up.
- **Checking it from production:**
    ```bash
    ssh dota.kettle.sh 'docker exec df-backend-1 python /app/backend/manage.py shell -c \
      "from lobby.client import DotaLobbyClient; print(DotaLobbyClient().list_lobbies())"'
    ```
- **Webhooks:** none are configured yet. When the receiver lands, dota_lobby will post to
  production's `/api/internal/` from the home cluster. That address must then be in
  `INTERNAL_SERVICE_ALLOWED_IPS`, and the signing secret set on both sides.

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
