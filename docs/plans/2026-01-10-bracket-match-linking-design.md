# Bracket Match Linking Design

**Date:** 2026-01-10
**Status:** Approved

## Purpose

Enable manual linking of tournament bracket games to Steam matches via a modal UI. Provides tiered match suggestions based on player/captain overlap, with search functionality.

## Summary

1. Add modal in MatchStatsModal to link/unlink Steam matches to bracket games
2. Tier suggestions: All Players > Captains + Some > Captains Only > Partial
3. Configure leagues via YAML + Pydantic Settings
4. Remove redundant GameStat model
5. Add Cypress tests with bracket linking test data

---

## Data Model Changes

### Remove GameStat Model

Delete `GameStat` from `backend/app/models.py` (lines 309-335). This model duplicates `PlayerMatchStats` from the steam app.

**Files to update:**
- `backend/app/models.py` - Remove GameStat class
- `backend/app/serializers.py` - Remove GameStatSerializer references
- `backend/app/admin.py` - Remove GameStat admin registration
- `backend/app/views/` - Remove any GameStat view references
- Create migration to drop the table

### League Configuration via YAML + Pydantic

**New file:** `backend/config/leagues.yaml`
```yaml
leagues:
  - id: 17929
    name: "DTX"
    default: true
```

**New file:** `backend/config/settings.py`
```python
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import yaml

class LeagueConfig(BaseModel):
    id: int
    name: str
    default: bool = False

class AppConfig(BaseSettings):
    leagues: list[LeagueConfig] = []

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @property
    def default_league_id(self) -> int | None:
        for league in self.leagues:
            if league.default:
                return league.id
        return self.leagues[0].id if self.leagues else None

    @property
    def league_choices(self) -> list[tuple[int, str]]:
        return [(l.id, l.name) for l in self.leagues]

# Load at module level
CONFIG_PATH = Path(__file__).parent / "leagues.yaml"
app_config = AppConfig.from_yaml(CONFIG_PATH)
```

**Update:** `backend/dtx/settings.py`
```python
from config.settings import app_config

# Make available globally
LEAGUE_CHOICES = app_config.league_choices
DEFAULT_LEAGUE_ID = app_config.default_league_id
```

### Add league_id to Tournament

```python
from django.conf import settings

class Tournament(models.Model):
    league_id = models.IntegerField(
        null=True,
        blank=True,
        default=settings.DEFAULT_LEAGUE_ID,
        help_text="Steam league ID for match linking"
    )
```

### Update GameMatchSuggestion

Add captain-aware tier field:

```python
class SuggestionTier(models.TextChoices):
    ALL_PLAYERS = 'all_players', 'All Players Match'
    CAPTAINS_PLUS = 'captains_plus', 'Both Captains + Some Players'
    CAPTAINS_ONLY = 'captains_only', 'Both Captains Only'
    PARTIAL = 'partial', 'Partial Player Overlap'

# Add to GameMatchSuggestion model
suggestion_tier = models.CharField(
    max_length=20,
    choices=SuggestionTier.choices,
    default=SuggestionTier.PARTIAL
)
```

---

## Backend API Endpoints

### Match Suggestions Endpoint

```
GET /api/steam/games/{game_id}/match-suggestions/
```

Returns available Steam matches for linking, filtered by tournament's league_id.

**Query params:**
- `search` - Filter by match_id or captain name

**Response:**
```json
{
  "suggestions": [
    {
      "match_id": 9000000001,
      "start_time": 1704567890,
      "duration": 2400,
      "radiant_win": true,
      "tier": "all_players",
      "tier_display": "All Players Match",
      "player_overlap": 10,
      "radiant_captain": {
        "steam_id": 76561198000000001,
        "username": "phantom_lancer",
        "avatar": "/media/avatars/...",
        "hero_id": 12
      },
      "dire_captain": {
        "steam_id": 76561198000000002,
        "username": "anti_mage",
        "avatar": null,
        "hero_id": 1
      }
    }
  ],
  "linked_match_id": null
}
```

### Tier Calculation Logic

**New file:** `backend/steam/services/match_suggestions.py`

```python
def calculate_suggestion_tier(match, radiant_team, dire_team):
    radiant_steam_ids = set(get_team_steam_ids(radiant_team))
    dire_steam_ids = set(get_team_steam_ids(dire_team))
    all_team_steam_ids = radiant_steam_ids | dire_steam_ids

    match_steam_ids = set(
        PlayerMatchStats.objects.filter(match=match)
        .values_list('steam_id', flat=True)
    )

    overlap = all_team_steam_ids & match_steam_ids

    radiant_captain_id = radiant_team.captain.steamid if radiant_team.captain else None
    dire_captain_id = dire_team.captain.steamid if dire_team.captain else None

    both_captains_present = (
        radiant_captain_id in match_steam_ids and
        dire_captain_id in match_steam_ids
    )

    if len(overlap) == 10:
        return SuggestionTier.ALL_PLAYERS
    elif both_captains_present and len(overlap) > 2:
        return SuggestionTier.CAPTAINS_PLUS
    elif both_captains_present:
        return SuggestionTier.CAPTAINS_ONLY
    else:
        return SuggestionTier.PARTIAL
```

### Link/Unlink Match Endpoints

```
POST /api/steam/games/{game_id}/link-match/
Body: { "match_id": 9000000001 }
```

```
DELETE /api/steam/games/{game_id}/link-match/
```

Both return updated game data.

---

## Frontend Components

### LinkSteamMatchModal

**Location:** `frontend/app/components/bracket/modals/LinkSteamMatchModal.tsx`

**Props:**
```typescript
interface LinkSteamMatchModalProps {
  isOpen: boolean;
  onClose: () => void;
  game: BracketMatch;
  onLinkUpdated: () => void;
}
```

**Modal Layout:**
```
+-------------------------------------------------------------+
|  Link Steam Match                                       [X] |
+-------------------------------------------------------------+
|  +-----------------------------------------------------+    |
|  | Search by Match ID or Captain name...               |    |
|  +-----------------------------------------------------+    |
|                                                             |
|  Currently Linked: Match #9000000001  [Unlink]              |
|  -----------------------------------------------------------+
|                                                             |
|  +- All Players Match -------------------------------------+|
|  |                                                         ||
|  |  +---------------------------------------------------+  ||
|  |  | Match #9000000002                                 |  ||
|  |  | Jan 5, 2026 - 8:45 PM                             |  ||
|  |  |                                                   |  ||
|  |  |   [Avatar]           VS          [Avatar]         |  ||
|  |  |  phantom_lancer                 anti_mage         |  ||
|  |  |   [Hero Icon]                   [Hero Icon]       |  ||
|  |  |                                                   |  ||
|  |  |                    [View Details]  [Link]         |  ||
|  |  +---------------------------------------------------+  ||
|  +---------------------------------------------------------+|
|                                                             |
|  +- Both Captains + Some Players --------------------------+|
|  |  ... more match cards ...                               ||
|  +---------------------------------------------------------+|
+-------------------------------------------------------------+
```

### SteamMatchCard

**Location:** `frontend/app/components/bracket/modals/SteamMatchCard.tsx`

```typescript
interface SteamMatchCardProps {
  match: MatchSuggestion;
  onLink: (matchId: number) => void;
  onViewDetails: (matchId: number) => void;
  isCurrentlyLinked: boolean;
}
```

**Captain display logic:**
- If captain has user link: show avatar + username
- If no user link: show blank avatar icon + steam_id
- Hero icon centered below

### Tier Badge Styles

```typescript
const TIER_STYLES = {
  all_players: {
    bg: 'bg-green-500/20',
    border: 'border-green-500',
    text: 'text-green-400'
  },
  captains_plus: {
    bg: 'bg-blue-500/20',
    border: 'border-blue-500',
    text: 'text-blue-400'
  },
  captains_only: {
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500',
    text: 'text-yellow-400'
  },
  partial: {
    bg: 'bg-gray-500/20',
    border: 'border-gray-500',
    text: 'text-gray-400'
  },
};
```

### Integration with MatchStatsModal

Add button in `MatchStatsModal.tsx`:

```typescript
<Button
  variant="outline"
  onClick={() => setShowLinkModal(true)}
>
  {game.steamMatchId
    ? `Linked: Match #${game.steamMatchId}`
    : 'Link Steam Match'
  }
</Button>

{showLinkModal && (
  <LinkSteamMatchModal
    isOpen={showLinkModal}
    onClose={() => setShowLinkModal(false)}
    game={game}
    onLinkUpdated={refreshBracket}
  />
)}
```

---

## Cypress Tests & Test Data

### Test Data Setup

**Update:** `backend/tests/populate.py`

Add new function:

```python
def populate_bracket_linking_scenario(force=False):
    """
    Creates a tournament with bracket and unlinked Steam matches
    for testing the match linking modal.

    Scenario:
    - Tournament "Link Test Tournament" with 4 teams
    - Bracket generated (6 games, all pending/unlinked)
    - 6 Steam matches in league 17929:
      - 2 matches: all 10 players match (tier: all_players)
      - 2 matches: both captains + 4 players (tier: captains_plus)
      - 2 matches: both captains only (tier: captains_only)
    """
```

**Update:** `populate_all()`:
```python
def populate_all(force=False):
    populate_users(force)
    populate_tournaments(force)
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
```

### Cypress Test File

**New file:** `frontend/tests/cypress/e2e/bracket-match-linking.cy.ts`

```typescript
describe('Bracket Match Linking', () => {
  beforeEach(() => {
    cy.login('staff');
    cy.visit('/tournaments/link-test-tournament/bracket');
  });

  describe('Full Flow: Bracket to Linked Match', () => {
    it('should open match modal and link a steam match', () => {
      // Click on first pending game node
      cy.get('[data-testid="match-node-w-1-0"]').click();

      // MatchStatsModal opens
      cy.get('[data-testid="match-stats-modal"]').should('be.visible');

      // Click link button
      cy.get('[data-testid="link-steam-match-btn"]').click();

      // LinkSteamMatchModal opens
      cy.get('[data-testid="link-steam-match-modal"]').should('be.visible');

      // Verify tier sections exist
      cy.get('[data-testid="tier-all_players"]').should('exist');
      cy.get('[data-testid="tier-captains_plus"]').should('exist');

      // Select first "All Players Match" suggestion
      cy.get('[data-testid="tier-all_players"]')
        .find('[data-testid="match-card"]')
        .first()
        .find('[data-testid="link-btn"]')
        .click();

      // Modal closes, verify link persisted
      cy.get('[data-testid="link-steam-match-modal"]').should('not.exist');
      cy.get('[data-testid="link-steam-match-btn"]')
        .should('contain', 'Linked: Match #');
    });
  });

  describe('Modal Functionality', () => {
    beforeEach(() => {
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();
    });

    it('should filter matches by search term', () => {
      // Search by match ID
      cy.get('[data-testid="match-search-input"]').type('9000000');
      cy.get('[data-testid="match-card"]')
        .should('have.length.greaterThan', 0);

      // Clear and search by captain name
      cy.get('[data-testid="match-search-input"]')
        .clear()
        .type('phantom_lancer');
      cy.get('[data-testid="match-card"]')
        .should('have.length.greaterThan', 0);
    });

    it('should show view details and open match stats', () => {
      cy.get('[data-testid="match-card"]')
        .first()
        .find('[data-testid="view-details-btn"]')
        .click();

      cy.get('[data-testid="dota-match-stats-modal"]')
        .should('be.visible');
    });

    it('should unlink an already linked match', () => {
      // First link a match
      cy.get('[data-testid="tier-all_players"]')
        .find('[data-testid="link-btn"]')
        .first()
        .click();

      // Reopen modal
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();

      // Verify "Currently Linked" section shows
      cy.get('[data-testid="currently-linked"]').should('be.visible');

      // Click unlink
      cy.get('[data-testid="unlink-btn"]').click();

      // Verify unlinked
      cy.get('[data-testid="link-steam-match-btn"]')
        .should('contain', 'Link Steam Match');
    });

    it('should allow linking to a different match', () => {
      // Link first match
      cy.get('[data-testid="match-card"]').first()
        .find('[data-testid="link-btn"]').click();

      // Reopen and link different match
      cy.get('[data-testid="match-node-w-1-0"]').click();
      cy.get('[data-testid="link-steam-match-btn"]').click();

      cy.get('[data-testid="match-card"]').eq(1)
        .find('[data-testid="link-btn"]').click();

      // Should update to new match
      cy.get('[data-testid="link-steam-match-btn"]')
        .invoke('text')
        .should('match', /Linked: Match #\d+/);
    });
  });
});
```

---

## Files to Modify

### Backend

| File | Change |
|------|--------|
| `backend/app/models.py` | Remove GameStat, add Tournament.league_id |
| `backend/app/serializers.py` | Remove GameStatSerializer |
| `backend/app/admin.py` | Remove GameStat admin |
| `backend/config/leagues.yaml` | New - league configuration |
| `backend/config/settings.py` | New - Pydantic config loader |
| `backend/dtx/settings.py` | Load league config |
| `backend/steam/models.py` | Add SuggestionTier to GameMatchSuggestion |
| `backend/steam/services/match_suggestions.py` | New - tier calculation logic |
| `backend/steam/views.py` | Add match-suggestions, link-match endpoints |
| `backend/steam/urls.py` | Add new endpoint routes |
| `backend/tests/populate.py` | Add populate_bracket_linking_scenario |

### Frontend

| File | Change |
|------|--------|
| `frontend/app/components/bracket/modals/LinkSteamMatchModal.tsx` | New component |
| `frontend/app/components/bracket/modals/SteamMatchCard.tsx` | New component |
| `frontend/app/components/bracket/modals/MatchStatsModal.tsx` | Add link button |
| `frontend/app/api/steam.ts` | Add API functions for suggestions/linking |
| `frontend/tests/cypress/e2e/bracket-match-linking.cy.ts` | New test file |

### Migrations

- Remove GameStat table
- Add Tournament.league_id field
- Add GameMatchSuggestion.suggestion_tier field
