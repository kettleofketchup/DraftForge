# Test Tournament Reference

This document describes the test tournaments created by `populate_test_tournaments()` and which features each one tests.

## Quick Reference

| Key | Tournament Name | Tests |
|-----|----------------|-------|
| `draft_not_started` | Draft Not Started | Draft initialization, captain selection UI |
| `draft_in_progress` | Draft In Progress | Draft continuation, live view polling |
| `draft_captain_turn` | Captain Turn Test | **Captain auth flow**, pick permissions, notifications |
| `draft_completed` | Draft Completed | Draft to bracket transition, team rosters |
| `bracket_partial` | Bracket Partial | Bracket progression, match results display |
| `bracket_complete` | Bracket Complete | Final standings, tournament history, bracket badges |
| `shuffle_draft_not_started` | Shuffle Draft Not Started | Shuffle draft initialization, MMR sorting |
| `shuffle_draft_in_progress` | Shuffle Draft In Progress | MMR-based pick order, tie resolution |
| `shuffle_draft_captain_turn` | Shuffle Draft Captain Turn | Captain auth with shuffle draft |

## Detailed Scenarios

### draft_not_started

**Purpose:** Test draft creation and initialization flow

- Tournament has 4 teams with captains assigned
- No draft object exists yet
- **Cypress tests:** Staff can initialize draft, draft style selection

### draft_in_progress

**Purpose:** Test active draft with partial completion

- Draft initialized with snake style
- 3 picks already made (4th captain's turn)
- **Cypress tests:** Draft round navigation, live view updates

### draft_captain_turn

**Purpose:** Test captain authentication and pick flow

- Draft initialized, 0 picks made (first captain's turn)
- **First captain is the test user** (pk=1)
- **Cypress tests:**
  - Captain can see pick button
  - Captain can make picks via API
  - Notification badge appears
  - Floating indicator appears
  - Auto-open modal on page visit

### draft_completed

**Purpose:** Test completed draft state

- All 16 picks made (4 teams x 4 picks each)
- Teams fully populated with 5 members each
- **Cypress tests:** Team roster display, bracket generation ready

### bracket_partial

**Purpose:** Test bracket with some games played

- Draft completed
- 2 bracket games with Steam match results
- **Cypress tests:** Match stats modal, bracket progression arrows

### bracket_complete

**Purpose:** Test fully completed tournament

- All 6 double-elimination games completed
- Full Steam match history with player stats
- **Cypress tests:** Final standings, winner display, match history, bracket badges

### shuffle_draft_not_started

**Purpose:** Test shuffle draft initialization

- Tournament with shuffle draft style ready to start
- **Cypress tests:** Shuffle draft initialization, MMR sorting

### shuffle_draft_in_progress

**Purpose:** Test active shuffle draft

- Shuffle draft with 2 picks made
- **Cypress tests:** MMR-based pick order, tie resolution

### shuffle_draft_captain_turn

**Purpose:** Test shuffle draft captain auth

- Shuffle draft where test user is captain
- **Cypress tests:** Captain auth with shuffle draft

## Helper Functions

### generate_steam_match()

Generate a Steam match with player statistics for testing.

```python
from tests.helpers.steam_match import generate_steam_match

# Basic usage - random winner
match = generate_steam_match(radiant_team, dire_team)

# Force specific winner
match = generate_steam_match(radiant_team, dire_team, radiant_win=True)

# Custom duration (seconds)
match = generate_steam_match(radiant_team, dire_team, duration=2400)

# Specific match ID (for reproducible tests)
match = generate_steam_match(radiant_team, dire_team, match_id=9000000999)
```

**Returns:** `Match` instance with `PlayerMatchStats` for all team members.

**Match ID Generation:** Uses prefix `9000000000` to avoid collisions with real Steam match IDs. The `generate_unique_match_id()` function tracks used IDs to ensure uniqueness within a test run.

### TestTournamentConfig

Create custom test scenarios with Pydantic validation.

```python
from tests.helpers.tournament_config import TestTournamentConfig

# Create custom test scenario
config = TestTournamentConfig(
    key="my_custom_test",
    name="My Custom Tournament",
    description="Tests a specific edge case",
    num_teams=4,
    draft_state="in_progress",
    picks_completed=7,
    first_captain_is_test_user=True,
)

tournament = config.create()
```

**Available Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | str | required | Unique identifier for tests |
| `name` | str | required | Tournament display name |
| `description` | str | required | What this tournament tests |
| `num_teams` | int | 4 | Number of teams to create |
| `tournament_type` | str | "double_elimination" | Tournament format |
| `draft_state` | str | "not_started" | "not_started", "in_progress", "completed" |
| `draft_style` | str | "snake" | "snake" or "normal" |
| `picks_completed` | int | 0 | Number of draft picks already made |
| `bracket_games_completed` | int | 0 | Number of bracket games with results |
| `first_captain_is_test_user` | bool | False | Set test user as first captain |

### reset_match_id_tracker()

Reset the match ID tracker between test runs to allow ID reuse.

```python
from tests.helpers.steam_match import reset_match_id_tracker

# Call at start of test suite
reset_match_id_tracker()
```

## Running Tests by Feature

```bash
# All tests
inv test.run

# Draft tests only
inv test.run --spec drafts

# Bracket tests only
inv test.run --spec bracket

# Mobile tests only
inv test.run --spec mobile

# Match stats tests only
inv test.run --spec match

# Specific test file
inv test.run --spec "tests/cypress/e2e/07-draft/01-captain-pick.cy.ts"
```

## Test User Conventions

| User | PK | Role | Purpose |
|------|-----|------|---------|
| test_user | 1 | Regular user | Captain in `draft_captain_turn` |
| test_staff | 2 | Staff | Admin operations testing |
| test_super | 3 | Superuser | Full admin testing |

These users are created by `createTestUser()`, `createTestStaffUser()`, and `createTestSuperUser()` in `backend/tests/test_auth.py`.

## Cypress Commands

### loginAsUser(pk)

Login as any user by primary key. Only works in TEST_MODE.

```typescript
cy.loginAsUser(42);
```

### loginAsTestUser()

Shortcut for `cy.loginAsUser(1)`.

```typescript
cy.loginAsTestUser();
```

### loginAsStaff()

Shortcut for `cy.loginAsUser(2)`.

```typescript
cy.loginAsStaff();
```

### loginAsCaptain(tournamentKey)

Login as the first captain of the specified test tournament.

```typescript
cy.loginAsCaptain('draft_captain_turn');
```

### getTournamentByKey(key)

Get tournament data by test config key.

```typescript
cy.getTournamentByKey('draft_in_progress').then((tournament) => {
  cy.visit(`/tournaments/${tournament.pk}`);
});
```

## Testing Brackets

### Bracket Structure

The test tournaments use 4-team double elimination brackets with the following structure:

```
Winners Bracket:
  R1: Match 0 (Team 0 vs Team 1) → Winners Final
  R1: Match 1 (Team 2 vs Team 3) → Winners Final
  R2: Winners Final → Grand Finals

Losers Bracket:
  R1: Losers Round 1 (Losers from W-R1) → Losers Final
  R2: Losers Final (Winner of L-R1 vs Loser of WF) → Grand Finals

Grand Finals:
  Winner of WF vs Winner of LF
```

### Bracket Badges

Bracket badges visually link winners bracket matches to their losers bracket destinations:

| Badge | Winners Match | Losers Destination |
|-------|--------------|-------------------|
| A | Winners R1 M1 (position=0) | Losers R1 radiant slot |
| B | Winners R1 M2 (position=1) | Losers R1 dire slot |
| C | Winners Final | Losers Final dire slot |

**Test IDs for Badges:**

- `[data-testid="bracket-badge-A-right"]` - Badge A on winners match
- `[data-testid="bracket-badge-A-left-top"]` - Badge A on losers radiant slot
- `[data-testid="bracket-badge-B-left-bottom"]` - Badge B on losers dire slot
- `[data-testid="bracket-badge-letter-A"]` - The letter element inside the badge

### Running Bracket Tests

```bash
# Run all bracket tests
inv test.spec --spec bracket

# Run specific bracket test file
cd frontend && npx cypress run --spec "tests/cypress/e2e/09-bracket/**/*.cy.ts"

# Open Cypress interactive mode for brackets
cd frontend && npx cypress open
# Then select 09-bracket tests
```

### Tournaments for Bracket Testing

| Tournament | PK | Bracket State | Best For Testing |
|------------|-----|---------------|------------------|
| Spring Championship | 1 | All 6 games completed | Full bracket with badges |
| Summer League | 2 | 2 games completed | Partial bracket progression |
| Autumn Cup | 3 | 0 games completed | Empty/pending bracket |

## Adding New Test Scenarios

1. Add a new `TestTournamentConfig` to `TEST_TOURNAMENTS` list in `backend/tests/helpers/tournament_config.py`

2. Run `populate_test_tournaments(force=True)` to recreate all tournaments

3. Update this documentation with the new scenario

4. Create corresponding Cypress tests

Example:

```python
TestTournamentConfig(
    key="swiss_tournament",
    name="Swiss Format Test",
    description="Tests Swiss bracket format with record tracking",
    num_teams=8,
    tournament_type="swiss",
    draft_state="completed",
    picks_completed=32,  # 8 teams x 4 picks
    bracket_games_completed=0,
),
```
