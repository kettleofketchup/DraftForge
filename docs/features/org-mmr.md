# Org MMR per game

Each organization member has one org MMR **per game**: a Dota 2 org MMR and a Deadlock
org MMR. Org staff assign these numbers. They are separate from the MMR or rank a player
enters on their own profile (`PlayerDotaProfile.mmr`, the Deadlock rank text), which
stays as it was.

Before this change a member had a single org MMR (`OrgUser.mmr`). Every existing value
was Dota MMR, and the upgrade moves it to the Dota 2 org MMR unchanged.

---

## Values and storage

- Values are stored one row per (membership, game) in `org.OrgUserGameMmr`
  (`org_user`, `game_type`, `mmr`, `updated_at`), unique on `(org_user, game_type)`.
- A game with no row reads as **0**, shown as "Not added" or "—".
- Clearing a value (empty input, `null` or `0`) deletes the row.
- All reads and writes go through `backend/org/mmr.py` (`get_org_mmrs`, `org_mmr_map`,
  `set_org_mmr`, `bulk_set_org_mmrs`, `merge_org_mmrs`). Writes validate the value and
  bust the member's tournament caches after commit.
- The Django admin shows the values read-only ("MMRs" column, e.g. `D2 4000 · DL 2500`).
  Edit them from the organization page instead.

### Scale

| Game | Meaning | Range |
|------|---------|-------|
| Dota 2 | Ranked MMR, as before | 0 – 20000 |
| Deadlock | A number the organization defines. Deadlock has no public MMR, so the scale is the org's own | 0 – 20000 |

On approval, Dota signups get a suggested value from the player's medal or
self-reported MMR. Deadlock signups get no suggestion. The approval dialog shows the
player's self-reported Deadlock rank and its date so staff have something to go on, and
the admin types the value.

---

## Which game a screen uses

| Where | Game |
|-------|------|
| Tournament pages, players tab, team cards, team totals, drafts, captain succession | The tournament's game |
| Event page, roll call, signup approval | The event's game |
| Organization Users tab, user card on the org page, player modal opened from the org page | Every game, each on its own line |
| League pages and league MMR (`LeagueUser.mmr`, league rating base MMR, match snapshots) | Always Dota 2 |
| Anything with no game | Dota 2 |

A Deadlock tournament therefore balances teams, orders shuffle drafts and picks a new
captain by Deadlock org MMR. Dota tournaments behave exactly as before.

### Limitations

- **Leagues are Dota only.** A league has no game, so league MMR is the Dota 2 org
  MMR plus the member's best league performance adjustment (`mmr_adjustment` from
  league stats). It is seeded that way when a member joins a league and recomputed
  for Unverified league MMRs whenever the org MMR or the adjustment changes. Official
  league MMRs stay pinned, a member without an org MMR keeps their league MMR, and a
  CSV import with the `league` MMR target writes the staff-entered value as is. The
  tournament CSV import refuses the `league` MMR target for a non-Dota tournament.
- **Deadlock tournaments come from events.** The tournament create form always makes a
  Dota 2 tournament (`game_type` is read-only there). Create a Deadlock event and start
  its tournament from the event.
- The Dota verification flags (`has_active_dota_mmr`, `dota_mmr_last_verified`) are set
  only by Dota writes.

---

## Editing

| Where | What you can edit |
|-------|-------------------|
| Organization page → Users → edit user | Every game's org MMR. Hotkeys: **R** Dota 2, **K** Deadlock |
| Tournament players tab → edit user | Only the tournament's game |
| Player modal from a tournament, draft, team or event | Only that surface's game |
| Event approval dialog | The event's game ("Set Deadlock org MMR"). The value is required; Deadlock needs at least 1 |
| CSV import (organization) | One game per import, chosen in the **Game** select (default Dota 2) |
| CSV import (tournament) | The tournament's game, shown as "MMR column applies to: …" |

An out-of-range stored value (see [Upgrading](#upgrading)) shows an error on its own
field. Fix or clear it before saving.

The API is listed in
[API Endpoints: Organization members](../api/endpoints.md#organization-members).

---

## Who can see it

The full per-game set (`game_mmrs`, `org_user_game_mmrs`, `target_game_mmrs`) is only
returned where org MMR was already restricted: the org Users endpoint and the PATCH
response, claim requests, and event signups for viewers who pass the org member rule.
Tournament, team and draft payloads carry only `mmr` for their own game plus
`mmr_game_type`. See [Roles](../dev/auth/roles.md).

Members can ask staff to change their org or league MMR with a screenshot, and staff
can mark a value Official. Profiles show each value with an Official or Unverified
badge. See [MMR update requests](mmr-update-requests.md).

---

## Upgrading

Migrations `org.0015` and `org.0016` create the table and copy every non-zero
`OrgUser.mmr` into a Dota 2 row; values outside 0–20000 are copied as they are and the
migration prints their OrgUser ids. `org.0018` then drops the old column, so the old containers must be stopped before it
runs. `just dev::release` stops the release stack before it migrates; the 0.18.0 release
notes carry the manual stop-first commands for the older recipe, and the rollback
steps. Rolling back `org.0018` refills the column from the Dota 2 rows and keeps every
per-game row.

---

## Adding a game

Adding a `GameType` needs no new column, table or data migration for org MMR. Follow the
canonical checklist in the module docstring of
`backend/events/discord/providers/registry.py`; the org MMR steps are 4 and 9–12
(`GameType`, `REQUIREMENT_CHECKS`, optional `MMR_BOUNDS`, and the frontend `GAME_*`
constants). `frontend/app/components/game/gameTypeSync.test.ts` fails when the
backend and frontend game lists or bounds drift.
