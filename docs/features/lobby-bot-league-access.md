# Lobby Bot League Access

A hosted Dota 2 lobby for a league game can only be created by a bot that is an admin of
the league's Steam league. When none of our bots is, the lobby fails with
`league_not_held`. The **Lobby bots** tab on the league page shows each of our lobby bots,
whether it has access to the league's Steam league, and the link to give Valve so a
missing bot gets access.

!!! info "GitHub Issue"
    [#909](https://github.com/kettleofketchup/DraftForge/issues/909)

---

## Who sees the tab

| Role | Sees the tab | Bots listed |
|------|--------------|-------------|
| Site admins (staff or superuser) | Yes | Every lobby bot |
| League admins | Yes | Only bots that already hold the league |
| Admins of the organization that owns the league | Yes | Only bots that already hold the league |
| League staff, org staff, members, everyone else | No | — |

Opening `/leagues/<league id>/lobby-bots` without access shows the league's info tab
instead. The API answers `404` to signed-in users who may not see the tab, so it does not
reveal whether a league exists.

!!! warning "Why league admins don't see the whole fleet"
    Any signed-in user can create an organization and a league, which makes them a
    league admin, and can enter any Steam league ID no other league has claimed. If
    league admins saw every bot, anyone could list our whole bot fleet and its Steam
    accounts. So only site admins get the full list. Other admins see the bots that
    already hold their Steam league, with a note: "Only bots that already have access
    to this league are listed. Ask a site admin for the profile links of the other
    lobby bots."

The tab needs the league's **Steam League ID** (Edit League). Without one it says "This
league has no Steam league ID. Add one in Edit League to check bot access." When hosted
lobbies are off for the site, it says "Hosted lobbies aren't enabled on this site."

---

## Reading the table

Bots are listed as **Bot 1**, **Bot 2** and so on. Their account names are never shown.
The summary above the table says how many bots can host lobbies in the Steam league.

### Status

Status is shown only for bots that hold the league; the others show **—**.

| Status | Meaning |
|--------|---------|
| Available | Online and free to host a lobby |
| Busy | Hosting a lobby now |
| Connecting | Logging on to Steam or Dota, or finishing its last lobby |
| Offline | Disconnected, backing off, stopped or waiting for an operator |
| Unknown | The lobby service reported a state DraftForge does not know |
| — | Not shown, because the bot does not hold this league |

### League access

| Access | Meaning |
|--------|---------|
| ✓ Verified | Dota's game coordinator lists the bot as an admin of the league. The time shows when that was last checked |
| Unverified | The bot is expected to hold the league but Dota has not confirmed it yet: its admin list has not been fetched since it logged on, or the league check failed for this page load |
| ✗ Missing | Dota has fetched the bot's admin list and the league is not on it. Add the bot (below) |
| Unknown | DraftForge could not find out, for example because the lobby service did not answer in time |

A small note can follow the access value:

- **not re-checked since the lobby service restarted**: the result comes from the lobby
  service's saved data and has not been fetched from Dota since it restarted. Press
  **Refresh access** to check again.
- **lobbies are still routed to it, but Valve doesn't list it as an admin**: the lobby
  service is configured to use the bot for this league anyway. Lobby creation may still
  fail until the bot is added.

!!! note "Unknown is not Missing"
    The tab only says **Missing** when Dota has answered and the league is not on the
    bot's list. When the lobby service is down, slow, or has not fetched a bot's list yet,
    the row says **Unknown** or **Unverified** instead. Being unable to ask is never read
    as "no access". If the whole lobby service is unreachable the tab says "The lobby
    service couldn't be reached, so bot access is unknown. Try again shortly." and shows
    no table.

The last column holds the bot's **Steam profile link** and a **Copy** button. A bot that
has never logged on shows "Not available until the bot logs on".

---

## Giving a bot access

There is no one-click link. DraftForge can't add a bot for you; the league owner adds it
on Valve's site:

1. On the Lobby bots tab, copy the missing bot's Steam profile link
   (`https://steamcommunity.com/profiles/<steam id>`). Only site admins see bots that
   don't hold the league yet, so league and organization admins get this link from a
   site admin.
2. Press **Open league admins page**. It opens
   `https://www.dota2.com/league/<league id>/admins`, where `<league id>` is the league's
   Steam League ID. You need to be signed in to Steam with an account that manages the
   league.
3. In the **League Administrators** section, add the bot by its Steam Community URL,
   pasting the profile link you copied.
4. If Steam asks you to log in first, reopen the league from your league list afterwards;
   the login may not return you to the admins page.
5. Back on the Lobby bots tab, press **Refresh access**. Valve can take a while to report a
   new admin, so the bot may stay **Missing** for a time after you add it.

---

## Refreshing access

The tab reads the lobby service each time it opens. **Refresh access** first asks every
online bot to re-fetch its admin list from Dota, then reloads the table. Rows stay on
screen whatever the result. A note above the table explains anything other than success:

| Note | Meaning |
|------|---------|
| The check is still running. Refresh again shortly. | Dota did not answer before the request timed out. The check may still finish |
| The lobby service couldn't be reached, so access wasn't re-checked. | The table shows the previous results |
| The lobby service can't re-check league access right now, so the last results are shown. | The lobby service is not set up to read admin lists from Dota |

A row can also note **bot not online, kept last result** or **check failed, kept last
result**.

Each user can load the tab 30 times and refresh it 6 times a minute, and refreshes are
capped at 20 a minute across the site. Past that, the tab says "Try again in N s".

!!! warning "Known limit"
    After the lobby service restarts, a bot whose saved admin list holds no leagues at all
    shows **Missing** rather than **Unknown** until the lobby service fetches its list
    again. Press **Refresh access** once the bot is online.

---

## API

| Method and path | What it does |
|-----------------|--------------|
| `GET /api/leagues/<league id>/bot-access/` | The bot access snapshot for the league |
| `POST /api/leagues/<league id>/bot-access/refresh/` | Re-check every bot's admin list, then return the snapshot with `refresh_outcome` and each row's `refresh` |

Both use the permissions above and answer `Cache-Control: no-store`. When the lobby service
fails they still answer `200`, with the problem in `service.status` (`unavailable`,
`error`, `disabled`, `not_configured`, `league_not_linked`, `unsupported`). A throttled
request gets `429` with `Retry-After` and `{"error": ..., "code": "throttled"}`.

Rows carry a position, status, access state and note, the check time and the bot's public
identity (`kind` and profile URL). `roster` is `all` for site admins and `holders` for
everyone else, whose rows are limited to bots that hold the league; `held_count` is then
the only count returned. Account names, error text and the lobby service address
are never returned.

---

## Adding another game

The backend seam is game-neutral; only Dota 2 has a provider today. Leagues have no game
type yet, so every league resolves to Dota 2, and an unregistered game gets the
`unsupported` snapshot ("Lobby bot management isn't available for this game yet.").

To add a game, follow the checklist in the docstring of
`backend/lobby/bot_access/registry.py`:

1. Implement a `BotAccessProvider` (`backend/lobby/bot_access/base.py`) in
   `backend/lobby/bot_access/<game>.py` and register it in `BOT_ACCESS_PROVIDERS`.
   `snapshot` and `refresh` take `full_roster`; when it is false, return only the bots
   that hold the league and set `roster="holders"`.
2. Add identity or link kinds in `backend/lobby/bot_access/schemas.py` if needed, then
   regenerate the frontend schemas with `just py::gen-bot-access-api`.
3. Add the game's copy under `frontend/app/features/bot-access/providers/`, keyed on the
   snapshot's `provider` value. Unknown providers fall back to neutral copy.
4. Teach `league_game_type` the league's game once leagues carry one.
5. Add provider tests next to `backend/lobby/tests/test_bot_access.py`.

See also [Dota 2 Lobbies](planned/dota-lobbies.md).
