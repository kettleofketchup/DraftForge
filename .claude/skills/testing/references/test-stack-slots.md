# Test Stack Slots

Full page: `docs/development/test-stack-slots.md`. Source: `scripts/slots.py`,
`just/test/mod.just`, `docker/docker-compose.slot*.yaml`,
`frontend/tests/playwright/fixtures/base-url{,-resolve}.ts`.

## Which port / which URL

| Slot | Project | Containers | URL |
|---|---|---|---|
| 0 | `df` | `frontend`, `backend`, `redis`, `nginx` | `https://localhost` (80/443) |
| N (1-9) | `df-sN` | `frontend-sN`, `backend-sN`, ... | `https://localhost:<10443+N*1000>` (HTTPS only) |
| dev | `df-dev` | `frontend-dev`, `backend-dev`, ... | `https://localhost` (80/443; not with slot 0) |

```bash
just test::slots   # read-only: every reservation and df* stack, owners, ports, lease age
just test::slot    # this worktree's slot (allocates if needed): DF_SLOT, project, DF_BASE_URL
```

Two worktrees never share a stack. A container named `backend` is slot 0's, which may
not be your worktree. Never hardcode `https://localhost`: Playwright code imports
`BASE_URL` / `API_URL` from `fixtures/base-url.ts`, and shell commands use the URL
`just test::slot` prints.

## Commands

| Command | Notes |
|---|---|
| `just test::upd` / `up` / `setup` / `build` / `pull` | Allocate or re-adopt the slot, then act on it |
| `just test::down` / `stop` / `logs` / `ps` / `exec` / `restart` | This slot only; error if no slot or it was taken |
| `just test::run '<cmd>'` | Never allocates; without a slot runs in a throwaway `df-run-<hex>` project |
| `just test::compose <args>` | Compose against this slot; `--stack dev` for `df-dev`. Use instead of raw `docker compose` / `docker exec <name>` |
| `just test::dota-lobby [up\|down\|restart\|logs\|ps]` | The simulated dota_lobby (service `dota-lobby`, profile `dota-lobby`) for the 18-dota-lobby specs. `up` runs the slot's `up -d` with the profile on |
| `just test::background on\|off` | Discord bot + celery beat + real tokens for this N ≥ 1 slot (one project at a time) |
| `just test::slot-release` | Release own slot (stack must be down) |
| `just test::slot-release --slot N` | Release someone else's idle slot. Pre-checks first (Rules) |
| `just test::slot-claim N` | Take slot N (owner must have no containers). Pre-checks first (Rules) |
| `just test::slot-reap <project>` | Remove an orphaned `df*` stack whose worktree is gone. Pre-checks first (Rules) |
| `just test::slot-reap --stale` | Reap every other slot whose last activity is older than 12h (`DF_SLOT_STALE_HOURS`) |
| `just test::slots-unit` | pytest for `scripts/slots.py` |

From another directory: `just -f <wt>/justfile -d <wt> <recipe>`.

## Externals

Slots N ≥ 1 with background off have no bot, no beat, and blank `DISCORD_BOT_TOKEN` /
`STEAM_API_KEY`. Specs that need real Discord (run on slot 0 or with
`background on`): `16-events/03-roll-call`, `04-discord-integration`,
`06-full-lifecycle`, `07-notification-dm`, `08-tournament-discord-lifecycle`. They
warn and skip their Discord assertions otherwise, so a pass there proves nothing about
Discord. Backend `events.tests.test_discord_integration` skips without the token;
`just test::run` prints a notice when it blanks it.

### dota_lobby simulator

`docker-compose.test.yaml` has a `dota-lobby` service behind the `dota-lobby` profile:
dota_lobby in simulation mode (`docker/dota-lobby/simulator.yaml` and
`simulator-secrets.yaml`), no Steam logon. It is off unless asked for, so `test::up`
and CI never pull it. Each slot runs its own (project-scoped name, no host port);
the backend reaches it at `http://dota-lobby:8080` and it posts webhooks to
`http://backend:8000/api/internal/lobbies/events/`. `docker/.env.test` turns lobbies
on with matching test-only values (API key, webhook secret, `INTERNAL_SERVICE_TOKEN`).

- Image: `DOTA_LOBBY_IMAGE` (default `ghcr.io/kettleofketchup/dota_lobby:${DOTA_LOBBY_IMAGE_TAG}`).
  `DOTA_LOBBY_IMAGE_TAG` defaults to a placeholder: set it to the first dota_lobby
  release with simulation mode. Until then, build it in dota_lobby (`just docker::build`,
  tag `ghcr.io/kettleofketchup/dota_lobby:local`) and run
  `DOTA_LOBBY_IMAGE=ghcr.io/kettleofketchup/dota_lobby:local just test::dota-lobby up`.
- `test::down`, `stop`, `kill` and `rm` add `--profile '*'` (`scripts/slots.py`
  `TEARDOWN_VERBS`), so the simulator never outlives its stack or holds its network.
- Lobbies live in memory: `just test::dota-lobby restart` forgets them all.
- Never point it at a real deployment: it sends `X-Dota-Lobby-Simulation: true` and
  made-up match IDs.

## Rules

- `slot-reap`, `slot-claim` and `slot-release --slot N` need no user approval. Before
  using one on another worktree's slot, check that nobody is using it:
  - owner worktree: `git -C <owner> --no-optional-locks status --short`, last commit,
    `find <owner> ... -mmin -120` for recent edits;
  - containers: `docker ps -a --filter label=com.docker.compose.project=<p>` start
    times, `docker logs --since 30m --tail 5 <name>`;
  - test processes: `pgrep -f 'playwright|pytest|manage.py test'` with
    `readlink /proc/<pid>/cwd` inside the owner worktree;
  - other Claude sessions: ListAgents; a busy peer may own the worktree.

  If in doubt, don't touch it. Full commands: `docs/development/test-stack-slots.md`.
- Slots whose last activity (lease, container start/log times, owner-worktree git and
  file mtimes) is older than 12h are reaped automatically when a worktree needs a new
  slot, with a notice on stderr.
- No host-wide docker commands (`docker stop $(docker ps -aq)`, `docker system prune`).
- Tear down only what you started, with `just test::down` in that worktree.
- Old-code worktrees (branches without slots) can kill or hijack slot stacks; merge
  main into a worktree before using its test stack. A vanished container may be
  another session's old-code `test::down`: check `docker events --since <time>`
  before calling it a defect.
- Rootless podman: frontend `EACCES` → `setfacl -R -m u:100999:rwX -m d:u:100999:rwX <wt>`
  then `just test::compose restart frontend nginx`. Redis `dump.rdb` owned by uid 999
  needs sudo: report it to the user.
