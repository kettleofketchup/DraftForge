# Populate System

Source: `backend/tests/data/` (models + definitions), `backend/tests/populate/` (DB creation)

## Data Models (`backend/tests/data/models.py`)

Pydantic models defining test entity schemas:

| Model | Key Fields |
|-------|-----------|
| `TestUser` | pk, username, nickname, discord_id, steam_id, steam_id_64, mmr, is_staff, is_superuser, org_id, league_id, positions |
| `TestPositions` | carry, mid, offlane, soft_support, hard_support (all int, default 3) |
| `TestOrganization` | pk, name, description, logo, rules_template, timezone, default_league_id, discord_server_id |
| `TestLeague` | pk, name, steam_league_id, description, rules, prize_pool, timezone, organization_names |
| `TestTeam` | pk, name, captain (TestUser), members (list[TestUser]), draft_order, tournament_name |
| `TestTournament` | pk, name, tournament_type, state, steam_league_id, league_name, date_played, teams, user_usernames, completed_game_count, match_id_base |
| `DynamicTournamentConfig` | pk (required), name, user_count, team_count, tournament_type, league_name, completed_game_count, match_id_base |

`TestUser.get_steam_id_64()` converts 32-bit to 64-bit Steam ID. `DynamicTournamentConfig.create()` creates tournament in DB.

## Data Definition Files (`backend/tests/data/`)

| File | Exports |
|------|---------|
| `users.py` | ADMIN_USER(1001), STAFF_USER(1002), REGULAR_USER(1003), CLAIMABLE_USER(1010), USER_CLAIMER(1011), ORG_ADMIN_USER(1020), ORG_STAFF_USER(1021), LEAGUE_ADMIN_USER(1030), LEAGUE_STAFF_USER(1031), TOURNAMENT_USERS(20), CSV_IMPORT_USERS(5) |
| `organizations.py` | DTX_ORG(pk=1), TEST_ORG(pk=2), CSV_ORG(pk=3), EVENTS_ORG(pk=7) + name constants |
| `leagues.py` | DTX_LEAGUE(pk=1, steam=17929), TEST_LEAGUE(pk=2, steam=17930), CSV_LEAGUE(pk=3, steam=17931), EVENTS_LEAGUE(pk=7, steam=17935) + name/id constants |
| `teams.py` | 4 real tournament teams, 2 herodraft demo teams, 4 bracket-unset-winner teams |
| `tournaments.py` | 6 DynamicTournamentConfig objects + REAL_TOURNAMENT_38, DEMO_HERODRAFT_TOURNAMENT, BRACKET_UNSET_WINNER_TOURNAMENT, CSV_IMPORT_TOURNAMENT |
| `league_stats.py` | STRIP_STATS_PLAYERS (users 7000-7009, fixed W/L sequences, tournament 250, match ids 9200000001+) and SHOWCASE_PLAYERS (60 seeded users 7100-7159, tournament 251, match ids 9200010001+) |
| `dota_lobby.py` | LOBBY_ORG, LOBBY_LEAGUE (steam=17940), LOBBY_FIXED_PASSWORD, LOBBY_ROLE_USERS (pk 7200-7204), team rosters (pk 7210-7233) |
| `__init__.py` | Re-exports all models + all constants from above files |

## Populate Functions (`backend/tests/populate/`)

Execution order in `populate_all(force=False)`:

```
1.  populate_organizations_and_leagues   → organizations.py
2.  populate_users                       → users.py (Discord API or mock)
3.  populate_test_auth_users             → users.py (9 specific PK users)
4.  populate_real_tournament_38          → tournaments.py
5.  populate_tournaments                 → tournaments.py (6 dynamic configs)
6.  populate_steam_matches               → steam_matches.py
7.  populate_bracket_linking_scenario    → bracket_linking.py
8.  populate_bracket_unset_winner_tournament → bracket_unset_winner.py
9.  populate_csv_import_data             → csv_import.py
10. populate_demo_tournaments            → demo.py
11. populate_user_edit_data              → user_edit.py
12. populate_events_data                 → events.py (Events Test Org/League, repeater, signup event)
13. populate_shuffle_tie_data            → shuffle_tie.py
...
... populate_dota_lobby_data             → dota_lobby.py (its org/league take auto pks, so it runs after every step that expects fixed pks)
last. populate_tournament_discovery      → tournament_discovery.py (runs last: its explicit pks would bump the auto-increment counters the steps above rely on)
```

Read `steps` in `populate_all()` for the exact current order.

### Key Functions

| Function | File | What it does |
|----------|------|-------------|
| `populate_organizations_and_leagues` | organizations.py | Creates all orgs + leagues from data definitions |
| `populate_users` | users.py | Creates 40-100 Discord users for DTX org. Falls back to mock data. |
| `populate_test_auth_users` | users.py | Creates 9 users with specific PKs, assigns org/league roles |
| `populate_tournaments` | tournaments.py | Auto-discovers DynamicTournamentConfig objects, creates them |
| `populate_csv_import_data` | csv_import.py | Creates CSV org/league/tournament, 5 users, generates fixture CSVs |
| `populate_dota_lobby_data` | dota_lobby.py | Lobby Test Org/League (steam 17940), "Lobby Test Series" (fixed password, paused) with one upcoming event + 4-team tournament, "Lobby Random Event" (random password) + 2-team tournament, "Lobby Lifecycle Tournament" (in progress). Manual lobby mode everywhere; users 7200-7233 with Steam account IDs. `reset_dota_lobby_data` and `dota_lobby_test_data` serve the test endpoints |
| `populate_org_features_data` | org_features.py | Features Test / Locked Features / Private Features orgs + leagues (pk=40-42, steam=17941-17943), role users 7300-7307, Discord-linked players 7310-7319 and past tournaments 260-263, then `reset_org_features_data` (feature switches, ledger, templates, events). `org_features_test_data` serves the `e2e/19-org-features` specs |
| `populate_tournament_discovery` | tournament_discovery.py | Discovery Home/Away/Open orgs + leagues (pk=30-32, steam=17950-17952), `discovery_member` (pk=1100, OrgUser of org 30 only) and tournaments 900-906 (home live/soon/later/finished/stale, away cup, open-signups cup whose source event is SIGNUPS_OPEN) with absolute 2099/2020 dates. Fixture for `e2e/03-tournaments/04-discovery.spec.ts` |
| `populate_events_data` | events.py | Creates Events Test Org (pk=7), league (pk=7), 21 users (pk=5000-5020), "Weekly Inhouse" repeater, "E2E Signup Event" |
| `populate_league_stats_data` | league_stats.py | Strip Stats Org/League (pk=20, steam=17938): 10 users with exact ticket-game sequences for rank, tie, streak, unranked and zero-game cases. The fixture the league-stats tests assert against |
| `populate_league_stats_showcase` | league_stats.py | League Stats Showcase Org/League (pk=21, steam=17939): 60 seeded users, 160 5v5 ticket matches (54 ranked, 3 newcomers, 3 idle) and an untimed 8-captain draft. For demos and manual checks; tests assert its shape, not exact values |

### Shared Utilities (`backend/tests/populate/utils.py`)

- `create_user(user_data, organization=None)` - Create user from Discord data, optionally with OrgUser
- `ensure_org_user(user, organization, mmr)` - Get or create OrgUser
- `ensure_league_user(user, org_user, league)` - Get or create LeagueUser
- `flush_redis_cache()` - Flush Redis after population
- `generate_mock_discord_members(count)` - Create mock Discord member data

## Running Populate

```bash
# Full populate (destroy + migrate + populate)
just db::populate::all

# Fresh populate (bypass cache)
just db::populate::fresh

# Specific function (in Docker; test::run bypasses daphne and uses this worktree's slot)
just test::run 'python manage.py shell -c "from tests.populate.csv_import import populate_csv_import_data; populate_csv_import_data(force=True)"'
```

## Adding New Populate Functions

1. Create data definitions in `backend/tests/data/` (unique PKs/steam_league_ids)
2. Export from `backend/tests/data/__init__.py`
3. Create `backend/tests/populate/{feature}.py` with `populate_{feature}_data(force=False)`
4. Wire into `populate_all()` in `backend/tests/populate/__init__.py` (imports + call + `__all__`)
5. See [feature-isolation.md](feature-isolation.md) for the full pattern
