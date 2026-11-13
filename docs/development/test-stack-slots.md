# Test Stack Slots

Every git worktree runs its own test stack. Each stack lives in a **slot**: a compose
project, a host HTTPS port and a base URL that belong to exactly one worktree. Several
worktrees can run Playwright at the same time without stopping or recreating each
other's containers.

The dev stack is separate. It is always compose project `df-dev`, one per machine.

!!! warning "Merge main into a worktree before using its test stack"
    Worktrees on branches without this feature still run the old code. There,
    `just test::down` / `test::stop` stop **every container on the host** (all slots,
    `df-dev`, anything else), and `just test::upd` recreates project `df` with that
    worktree's mounts, taking slot 0 from whoever holds it. The new code can only
    detect a takeover and name the culprit; it cannot prevent it.

## Slot model

| | Slot 0 | Slot N (1-9) |
|---|---|---|
| Compose project | `df` | `df-sN` |
| Containers | `frontend`, `backend`, `redis`, `nginx`, `df-celery-*-1`, `df-discord-bot-1` | `frontend-sN`, `backend-sN`, `redis-sN`, `nginx-sN`, `df-sN-celery-*-1` |
| HTTPS port | 443 | `10443 + N*1000` (11443, 12443, ... 19443) |
| HTTP port | 80 | not published |
| Hostname | `localhost` | `sN.localhost` |
| Base URL | `https://localhost` | `https://sN.localhost:1N443` |
| Discord bot + celery beat | on | off (`just test::background on` to enable) |
| Discord/Steam tokens | real | blanked while background is off |
| Redis data | volume `df_redis_data` | volume `df-sN_redis_data` |

There are 10 slots (0-9). Slot 0 is exactly the stack CI and older docs assume.
Slots N ≥ 1 publish HTTPS only: nginx's HTTP→HTTPS redirect drops the port, so an HTTP
port would send the browser to slot 0.

### Hostnames

Each slot N ≥ 1 has its own hostname as well as its own port, because browsers scope
cookies by host and ignore the port. With one host per slot, each slot gets its own
cookie jar (session, CSRF, `df-locale`, Django `messages`), the way production has one
host per stack.

- Chromium (Playwright's included), Firefox, curl, and glibc with `nss-myhostname` or
  systemd-resolved resolve `*.localhost` to loopback, so `/etc/hosts` needs no entries.
  Check with `getent hosts s1.localhost`.
- Every slot keeps its own nginx on its own port. There is no shared listener that
  routes by `Host`, so one slot's nginx cannot take the others down, and rootless podman
  needs no privileged port beyond slot 0's 443.
- nginx has a single server block, so it serves any `Host`. It forwards the hostname
  without the port, so Django sees `sN.localhost`. Test and dev settings allow
  `.localhost` in `ALLOWED_HOSTS`, and `DF_EXTRA_CSRF_ORIGINS` / `SITE_URL` are the
  slot's base URL.
- Vite allows `.localhost`, and the HMR client connects to the page's own hostname.
- The self-signed cert in `nginx/data/ssl/` covers `localhost`, `*.localhost`,
  `s1.localhost` through `s9.localhost` (listed one by one because some TLS clients
  reject a wildcard directly under a TLD) and `nginx`.
  `nginx/data/ssl/gen_cert.sh` regenerates it from `cert.key`. If your browser trusted
  the old cert, trust the new one.
- `https://localhost:1N443` still reaches slot N, but it shares slot 0's cookie jar.
  Use the URL `just test::slot` prints.

The dev stack (`df-dev`) uses containers `frontend-dev`, `backend-dev`, `redis-dev`,
`nginx-dev`, `backend/.redis_data-dev`, and ports 80/443. It cannot run at the same
time as test slot 0; the helper refuses before any container starts.

### Where the state lives

- `docker/.env.slot` (gitignored, per worktree): `DF_SLOT`, `DF_SUFFIX`,
  `COMPOSE_PROJECT_NAME`, `DF_HTTPS_PORT`, `DF_HTTP_PORT`, `DF_BASE_URL`,
  `DF_BACKGROUND`, `DF_WORKTREE`, `DF_SLOT_TOKEN`, `DF_REGISTRY`. Only
  `DF_BACKGROUND` is user-controlled (through `just test::background`); the rest is
  rewritten on every allocation. Do not edit it or copy it to another worktree.
- Registry: `<git common dir>/df-slots/slot-N`, shared by every worktree of the repo.
  Each reservation records the owner worktree, a token and a `last_used` lease.

### Allocation

The first allocating verb in a worktree (`test::up`, `upd`, `setup`, `build`, `pull`,
or `just test::slot`) picks a slot, in this order:

1. this worktree's existing, valid reservation;
2. a slot whose running containers already belong to this worktree (adoption; this is
   how a pre-slots `df` stack becomes slot 0 for the worktree that started it);
3. the lowest free slot: no live reservation, no foreign containers, ports free.

Before steps 2 and 3, allocation reaps every other worktree's slot (0 included) whose
**last activity is older than 12 hours** (see [Auto-reap](#auto-reap)).

If no slot is free after that, an N ≥ 1 reservation with **zero containers** and a
lease older than **7 days** is reclaimed (oldest first).
Otherwise allocation fails and lists every reservation with its owner, container count
and lease age. `DF_SLOT=<n>` in the environment requests one specific slot.

Read verbs (`ps`, `logs`, `top`, `exec`, `restart`, `down`, `stop`, Playwright tasks)
never allocate. They fail if the worktree has no slot, or if another worktree has
taken it since (`slot N now belongs to <owner>; run just test::slot`).

`just test::run` never allocates either. With a slot it runs in that slot's project and
stops whatever it started; without one it uses an ephemeral `df-run-<hex>` project
that is removed afterwards.

## Commands

| Command | What it does |
|---|---|
| `just test::slot` | Allocate or re-adopt this worktree's slot and print it (slot, project, URL, ports, background) |
| `just test::slots` | List every reservation and every `df`, `df-sN`, `df-dev`, `df-run-*` project on the host, with owners, container counts and lease ages. Read-only; safe from any checkout |
| `just test::slot-release` | Release this worktree's slot. Refuses while its containers exist; run `just test::down` first |
| `just test::slot-release --slot N` | Release another worktree's reservation N, only if `df-sN` (or `df`) has zero containers. Run the [pre-checks](#before-touching-another-worktrees-slot) first |
| `just test::slot-claim N` | Move slot N to this worktree (releases this worktree's current slot first). Needs the current owner to have zero containers and the ports free. Run the [pre-checks](#before-touching-another-worktrees-slot) first |
| `just test::slot-reap <project>` | `down -v --remove-orphans` an orphaned `df`, `df-sN`, `df-dev` or `df-run-<hex>` project whose owner worktree no longer exists, and drop its reservation. Refuses while the owner is a live worktree. Run the [pre-checks](#before-touching-another-worktrees-slot) first |
| `just test::slot-reap --stale` | Run the [auto-reap](#auto-reap) sweep now and print what it removed |
| `just test::background on\|off` | Enable or disable the Discord bot and celery beat (and real tokens) for this slot. `on` refuses if a bot or beat already runs in another project. Takes effect on the next `test::upd` |
| `just test::compose <args>` | Run `docker compose` against this worktree's slot with the right `-p` and `-f` files. `--stack dev` targets `df-dev`; `--as-slot 0 config` renders slot 0's config without allocating |
| `just test::slots-unit` | Slot helper unit tests (pytest, no containers) |

`just test::down` and `just test::stop` act only on this worktree's project. Use
`just test::compose` instead of raw `docker compose` or `docker exec <name>`: raw
compose has no `-p` and resolves to project `df`, which may be another worktree's
stack.

Run recipes for a specific worktree with
`just -f <worktree>/justfile -d <worktree> <recipe>`.

## Bot, beat and external services

Every stack shares one `DISCORD_BOT_TOKEN`, one real guild and one Steam API key.
Discord rate-limits per token, and each bot that connects re-syncs the guild's slash
commands and receives every interaction. So:

- **Discord bot and celery beat run in one stack at a time.** Slot 0 (and dev) run them;
  slots N ≥ 1 scale both to zero. `just test::background on` turns them on for one
  N ≥ 1 stack, and the helper refuses if another project already runs either.
- **While background is off, slots N ≥ 1 also blank `DISCORD_BOT_TOKEN` and
  `STEAM_API_KEY`** on backend, celery and the bot
  (`docker/docker-compose.slot-offline.yaml`). Discord and Steam calls from request
  handlers and `celery-worker` then fail fast locally instead of writing to the real
  guild.
- **CI runs celery beat; slots N ≥ 1 do not.** CI's stack disables only the bot
  (`ci.override.yaml`). Beat-scheduled work (Discord event sync, reminders, avatar and
  Steam league sync) is exercised on slot 0 and in CI, not on an N ≥ 1 slot with
  background off.

### Specs that need real Discord

Run these on slot 0, or with `just test::background on`. On an N ≥ 1 slot with
background off they still pass, but they skip or warn past their Discord assertions,
so they prove nothing about Discord:

| Spec | What it needs |
|---|---|
| `e2e/16-events/03-roll-call.spec.ts` | Discord announcement; the "no re-announcement" check is vacuous without one |
| `e2e/16-events/04-discord-integration.spec.ts` | Announcement and signup posts in the test channels |
| `e2e/16-events/06-full-lifecycle.spec.ts` | Announcement posting and Discord activity logs |
| `e2e/16-events/07-notification-dm.spec.ts` | Sends a real DM through the bot token |
| `e2e/16-events/08-tournament-discord-lifecycle.spec.ts` | Draft and herodraft link DMs (Discord tournament logs) |

Other specs mention Discord only through populated Discord IDs, `loginAsDiscordId` or the
"Login with Discord" label, and need no external service. No e2e spec calls the real
Steam API; Steam match specs use populated data.

### Simulated dota_lobby

The dota_lobby integration specs (`e2e/18-dota-lobby/`) run against the real dota_lobby
service in simulation mode: simulated bots, players and matches, no Steam logon. It is
the `dota-lobby` service in `docker-compose.test.yaml`, behind the `dota-lobby` compose
profile, so `just test::up`, `test::setup` and CI never start or pull it.

```bash
# Until a dota_lobby release with simulation mode exists, build it in dota_lobby
# (`just docker::build`, tag ghcr.io/kettleofketchup/dota_lobby:local) and use that:
DOTA_LOBBY_IMAGE=ghcr.io/kettleofketchup/dota_lobby:local just test::dota-lobby up
just test::pw::dota-lobby          # the 18-dota-lobby specs, in order
just test::dota-lobby logs         # follow it; also down, restart, ps
```

- **Image:** `DOTA_LOBBY_IMAGE`, default `ghcr.io/kettleofketchup/dota_lobby:${DOTA_LOBBY_IMAGE_TAG}`.
  The tag defaults to `0.2.0`, the first dota_lobby release with simulation mode; bump the
  default in `docker-compose.test.yaml` (and `scripts/slot_tests/test_compose_files.py`)
  to take a newer release.
- **Config:** `docker/dota-lobby/simulator.yaml` (three bots that administer the
  Lobby Test League, auto join, auto start, a 5 s post-game linger) and
  `simulator-secrets.yaml`. Every secret in them is a test-only value that
  `docker/.env.test` repeats for the backend and Celery: `DOTA_LOBBY_API_KEY`,
  `DOTA_LOBBY_WEBHOOK_SECRET` and `INTERNAL_SERVICE_TOKEN` (the simulator sends it
  with each webhook). `docker/.env.test` also sets `DOTA_LOBBY_ENABLED=true` and
  `DOTA_LOBBY_URL=http://dota-lobby:8080`, so test stacks have lobbies on even without
  the simulator; the backend unit tests still start with them off
  (`backend/backend/test_runner.py`).
- **Per slot:** the container name is project-scoped and it publishes no port, so every
  slot runs its own. It posts webhooks to its own stack's backend.
- **Teardown:** `test::down`, `stop`, `kill` and `rm` add `--profile '*'`, so the
  simulator goes with its stack.
- **State:** lobbies live in memory and the database on a tmpfs: `just test::dota-lobby
  restart` starts from nothing.
- **Without it,** the specs that need it skip. `just test::pw::dota-lobby` and
  `cicd-dota-lobby` set `DOTA_LOBBY_SIMULATOR_REQUIRED=1` when this slot's simulator is
  running, so a simulator that is up but never becomes available within 60 s (bots not
  ready, test league not verified) fails the run rather than skipping it.
  `03-password-visibility` falls back to a seeded lobby row and `05-modal-fit` needs
  only lobbies on: both always run, CI included.

### Backend suites that skip without tokens

`events.tests.test_discord_integration` (with helpers in `discordbot/test_utils.py`)
skips every test when `DISCORD_BOT_TOKEN` is empty. `just test::run` blanks the tokens
whenever it runs without a slot or on an N ≥ 1 slot with background off, and prints a
notice saying so. Run it from the slot-0 worktree, or turn background on, for a real
Discord run.

## Playwright base URL

Playwright never allocates a slot. `frontend/tests/playwright/fixtures/base-url.ts`
exports `BASE_URL` and `API_URL` and resolves them at import time:

1. `DF_BASE_URL` from the environment. `just test::pw::*` and `just demo::*` set it
   from `python -m scripts.compose env` with `DF_BASE_URL_SOURCE=runner`
   (`https://nginx` with source `container` inside a container). Any other export that
   disagrees with this worktree's slot file is rejected.
2. Otherwise `docker/.env.slot`, after checking that it belongs to this worktree and
   that the registry still gives this worktree that slot.
3. Otherwise `https://localhost` when `GITHUB_ACTIONS=true` (CI).
4. Otherwise it throws `No test-stack slot for this worktree. Run "just test::slot".`

Never write `https://localhost` or read `DOCKER_HOST` in specs, fixtures or configs. A
vitest guard (`frontend/tests/unit/playwright-literal-guard.test.ts`) fails on either.

## Cookie names

Browsers scope cookies by host, not port, so every slot shares one cookie jar for
`localhost`. To keep a login on one slot from logging you out of another, slots N ≥ 1
suffix their cookie names: `sessionid-sN` and `csrftoken-sN`. Ephemeral `just test::run`
stacks do the same with their `-run-<hex>` suffix.
`docker-compose.slot.yaml` sets `DF_SESSION_COOKIE_NAME` and `DF_CSRF_COOKIE_NAME` on
the backend and `VITE_CSRF_COOKIE_NAME` on the frontend, which reads the CSRF cookie
for the `X-CSRFToken` header. Slot 0, CI and production keep Django's default names.

`VITE_CSRF_COOKIE_NAME` is fixed when the dev server starts or the image is built, so it
is only the starting guess. Every backend response carries an `X-CSRF-Cookie-Name`
header, and the axios client switches to that name (logging a `csrf` warning) when it
differs. A stale frontend container or a prebuilt image on a slot therefore recovers
after its first API response instead of failing every write with a 403.

Cookies read in the browser go through `readCookie` in `frontend/app/lib/cookies.ts`,
which matches the exact name and URL-decodes the value.

Other cookies stay shared on purpose:

- `df-locale` (the frontend's language choice) is a display preference of the person at
  the browser, not tied to a stack's data or login. Sharing it across slots is harmless.
- Django never sets its language cookie here: there is no `LocaleMiddleware` and no
  `set_language` view.
- Django's `messages` cookie only carries flash messages for Django-rendered pages
  (admin, social-auth errors). The React app never reads it; at worst a message shows
  up in another slot's admin.

In Playwright fixtures, find cookies with `isCsrfCookie` / `isSessionCookie` from
`fixtures/cookies.ts` rather than comparing against `csrftoken` or `sessionid`.

## CI

CI has no slot file and never allocates. With `GITHUB_ACTIONS=true` the helper uses a
synthetic slot 0: project `df`, `docker-compose.test.yaml` +
`docker-compose.ci.override.yaml`, `https://localhost`, no registry, no probes. CI
workflow files are unchanged.

## Known limitations

- **Real Discord OAuth login works on slot 0 only.** Nginx forwards `Host: sN.localhost`
  without the port, and the Discord app registers only `https://localhost` redirect
  URIs, so the OAuth `redirect_uri` (and mail links built from the request) do not
  work on N ≥ 1. Log in through the test-login endpoints there.
- **Dev images are shared.** `ghcr.io/kettleofketchup/draftforge/{backend-dev,frontend-dev,nginx}:latest`
  are the same for every slot. `just test::setup` rebuilds them, so a worktree that
  changes Python/npm dependencies or Dockerfiles affects other stacks the next time
  they are recreated. `test::setup` warns about this on N ≥ 1. The test-db image is
  keyed by content hash, so schema changes do not leak between worktrees.
- **Frontend caches are shared within one worktree.** A test slot and `df-dev` started
  from the same worktree both mount `./frontend` and share `node_modules/.vite`,
  `node_modules/.cache` and `.react-router/`. Do not set `VITE_FORCE_OPTIMIZE=true`
  while two stacks run from one worktree: the frontend entrypoint deletes all three
  under the other stack.

## After upgrading

- A test stack already running as project `df` is adopted as slot 0 by the worktree
  that started it; nothing is recreated. Other worktrees get N ≥ 1.
- A **legacy dev stack** still running as project `df` (started from
  `docker-compose.debug*.yaml` before the rename to `df-dev`) blocks slot 0, and dev
  verbs print a note about it. `just dev::down` now targets `df-dev` and cannot reach
  it. The allocator prints the exact one-time cleanup and never runs it:

    ```bash
    docker compose -p df -f <its config file> --project-directory <its working_dir> down
    ```

    A human runs this. Agents ask the user; the project's just-interceptor rewrites
    raw `docker compose ... down` to `just test::down` anyway.

- `DOCKER_HOST` no longer sets the Playwright host. Unset any `DF_BASE_URL` you exported
  by hand.
- Slots N ≥ 1 moved from `https://localhost:1N443` to `https://sN.localhost:1N443`. The
  next allocating verb (`just test::slot`, `test::upd`) rewrites `docker/.env.slot`;
  until then Playwright keeps using the old URL, which still works.

## Auto-reap

A slot's **last activity** is the latest of:

- the reservation's `last_used` (written on every allocation, `test::up`/`upd` and
  `test::run`);
- the project's containers: each one's start and finish time, plus the timestamp of
  the last log line of each running container;
- the owner worktree (and the working dir of each container): mtimes of its git
  `index`, `HEAD` and `logs/HEAD`, `docker/.env.slot`, `frontend/test-results`,
  `frontend/playwright-report`, and every modified or untracked file
  (`git ls-files -m -o --exclude-standard`, first 500).

When an allocating verb (`test::up`, `upd`, `setup`, `build`, `pull`, `just test::slot`)
needs a new slot, it reaps every other worktree's slot whose last activity is older
than 12 hours: `docker compose -p <project> down -v --remove-orphans` when the project
has containers, then the reservation is removed. Each reap prints a notice:

```text
auto-reaped slot 3 (df-s3), owner /path/to/wt: idle 20.1h > 12h (last activity: containers); 4 container(s) and volumes removed
```

A slot is never auto-reaped when:

- any signal above is within 12 hours (this protects slot 0's live stack too);
- the project has containers but their activity cannot be read;
- any container in it comes from a non-test compose file (a legacy dev or prod stack
  in `df`);
- it belongs to this worktree.

`DF_SLOT_STALE_HOURS` overrides the 12-hour threshold. `just test::slot-reap --stale`
runs the sweep on demand. `just test::slots` stays read-only and only notes when a
reservation's lease is past the threshold. CI never reaps.

## Before touching another worktree's slot

`just test::slot-reap`, `just test::slot-claim` and `just test::slot-release --slot N`
run without user approval. Before running one against a slot this worktree does not
own, verify that no other agent is working in or testing against it. If any check
shows recent activity, or you are unsure, leave the slot alone and use another one.

1. **Owner worktree.** Take the owner from `just test::slots`, then:

    ```bash
    git -C <owner> --no-optional-locks status --short
    git -C <owner> log -1 --format='%cr  %s'
    find <owner> \( -name node_modules -o -name .git \) -prune -o -type f -mmin -120 -print | head
    ```

    Uncommitted changes, a recent commit or files modified in the last hours mean
    someone is working there. `--no-optional-locks` keeps `git status` from touching
    the index (which auto-reap counts as activity).

2. **Containers in the project.**

    ```bash
    docker ps -a --filter label=com.docker.compose.project=<project> --format '{{.Names}}  {{.Status}}  {{.RunningFor}}'
    docker logs --since 30m --tail 5 <container>
    ```

    Recently started containers or fresh log lines (requests hitting nginx or the
    backend) mean a stack is in use.

3. **Test processes in that worktree.**

    ```bash
    for p in $(pgrep -f 'playwright|pytest|manage.py test|vitest'); do
      printf '%s %s\n' "$p" "$(readlink /proc/$p/cwd)"
    done | grep -F <owner>
    ```

    Any hit means a test run is going on against that worktree's slot.

4. **Other Claude sessions.** ListAgents shows peer sessions. A busy session may own
   the worktree even when the checks above look quiet (it may be between runs).
   Also look for a `claude` process whose cwd is the owner worktree:
   `for p in $(pgrep -x claude); do readlink /proc/$p/cwd; done | grep -F <owner>`.

If in doubt, don't touch it.

## Rules for agents

- Find URLs and ports with `just test::slots` / `just test::slot`; never hardcode
  `https://localhost`.
- Use `just test::compose` for compose commands; never raw `docker compose`,
  `docker exec <name>` or host-wide commands such as `docker stop $(docker ps -aq)`.
- `just test::slot-reap`, `just test::slot-claim` and `just test::slot-release --slot N`
  need no user approval, but they act on another worktree's state: run the
  [pre-checks](#before-touching-another-worktrees-slot) first.
- Tear down what you start with `just test::down` in the same worktree.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No test-stack slot for this worktree` | `just test::slot` |
| `slot N now belongs to <owner>` / `slot N was reclaimed while idle` | Another worktree took the slot. `just test::slot` allocates a new one if this worktree has no containers left in the old project |
| `` `df` was taken over by <path> `` | An old-code worktree ran `test::upd`. Merge main into that worktree |
| No free slot | `just test::slots`; release idle slots you own, or run the [pre-checks](#before-touching-another-worktrees-slot) and `just test::slot-release --slot N` |
| Port already in use on `up` | `just test::slots` shows which project holds it; dev and test slot 0 cannot run together |
| Redis fails to start, permission denied on `dump.rdb` (dev stack) | Rootless podman: `backend/.redis_data-dev/dump.rdb` is owned by the container's uid 999 (a subuid on the host). Remove the directory without sudo: `podman unshare rm -rf backend/.redis_data-dev`. Test stacks use the named volume `<project>_redis_data` and do not hit this. If that fails, ask the user |
| Frontend `EACCES` writing the worktree | Rootless podman maps the frontend user to uid 100999. Run `setfacl -R -m u:100999:rwX -m d:u:100999:rwX <worktree>`, then `just test::compose restart frontend nginx` (restart **both**: nginx caches the frontend upstream IP) |
| Orphan stacks (owner worktree deleted) | `just test::slots` flags them; run the [pre-checks](#before-touching-another-worktrees-slot), then `just test::slot-reap <project>` |
