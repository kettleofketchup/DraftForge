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
| `organizations.py` | DTX_ORG(pk=1), TEST_ORG(pk=2), CSV_ORG(pk=3) + name constants |
| `leagues.py` | DTX_LEAGUE(pk=1, steam=17929), TEST_LEAGUE(pk=2, steam=17930), CSV_LEAGUE(pk=3, steam=17931) + name/id constants |
| `teams.py` | 4 real tournament teams, 2 herodraft demo teams, 4 bracket-unset-winner teams |
| `tournaments.py` | 6 DynamicTournamentConfig objects + REAL_TOURNAMENT_38, DEMO_HERODRAFT_TOURNAMENT, BRACKET_UNSET_WINNER_TOURNAMENT, CSV_IMPORT_TOURNAMENT |
| `__init__.py` | Re-exports all models + all constants from above files |

## Populate Functions (`backend/tests/populate/`)

Execution order in `populate_all(force=False)`:

```
1. populate_organizations_and_leagues   → organizations.py
2. populate_users                       → users.py (Discord API or mock)
3. populate_test_auth_users             → users.py (9 specific PK users)
4. populate_real_tournament_38          → tournaments.py
5. populate_tournaments                 → tournaments.py (6 dynamic configs)
6. populate_steam_matches               → steam_matches.py
7. populate_bracket_linking_scenario    → bracket_linking.py
8. populate_bracket_unset_winner_tournament → bracket_unset_winner.py
9. populate_csv_import_data             → csv_import.py
10. populate_demo_tournaments           → demo.py
```

### Key Functions

| Function | File | What it does |
|----------|------|-------------|
| `populate_organizations_and_leagues` | organizations.py | Creates all orgs + leagues from data definitions |
| `populate_users` | users.py | Creates 40-100 Discord users for DTX org. Falls back to mock data. |
| `populate_test_auth_users` | users.py | Creates 9 users with specific PKs, assigns org/league roles |
| `populate_tournaments` | tournaments.py | Auto-discovers DynamicTournamentConfig objects, creates them |
| `populate_csv_import_data` | csv_import.py | Creates CSV org/league/tournament, 5 users, generates fixture CSVs |

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

# Specific function (in Docker)
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py shell -c "from tests.populate.csv_import import populate_csv_import_data; populate_csv_import_data(force=True)"
```

## Adding New Populate Functions

1. Create data definitions in `backend/tests/data/` (unique PKs/steam_league_ids)
2. Export from `backend/tests/data/__init__.py`
3. Create `backend/tests/populate/{feature}.py` with `populate_{feature}_data(force=False)`
4. Wire into `populate_all()` in `backend/tests/populate/__init__.py` (imports + call + `__all__`)
5. See [feature-isolation.md](feature-isolation.md) for the full pattern
