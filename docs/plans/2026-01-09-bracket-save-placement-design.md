# Bracket Save + Team Placement Design

**Date:** 2026-01-09
**Status:** Approved

## Problem

1. `save_bracket` endpoint is a stub - bracket data doesn't persist to database
2. No tracking of team placement/ranking within tournaments
3. Need foundation for future player rewards/penalties based on placement

## Solution Overview

1. Implement `save_bracket` to persist frontend-generated bracket as `Game` records
2. Add `placement` field to `Team` model
3. Auto-calculate placement when teams are eliminated, with manual override capability

## Database Changes

### Team Model

Add placement field:

```python
placement = models.PositiveSmallIntegerField(
    null=True,
    blank=True,
    help_text="Final tournament placement (1=winner, 2=runner-up, etc.)"
)
```

## API Endpoints

### Save Bracket (Implement)

```
POST /bracket/tournaments/{tournament_id}/save/
Body: { "matches": [...] }
```

**Implementation:**

1. Validate tournament exists and user has admin permission
2. Delete existing bracket Games for this tournament
3. Two-pass Game creation:
   - Pass 1: Create all Game records without FK relationships, store id→pk mapping
   - Pass 2: Wire up `next_game` and `loser_next_game` using the mapping
4. Return saved games with database PKs

**Frontend Match → Backend Game Mapping:**

| Frontend | Backend |
|----------|---------|
| `id` (e.g., "w-1-0") | Used to resolve relationships, then discarded |
| `gameId` | `pk` (assigned on save) |
| `round` | `round` |
| `position` | `position` |
| `bracketType` | `bracket_type` |
| `eliminationType` | `elimination_type` |
| `radiantTeam.pk` | `radiant_team_id` |
| `direTeam.pk` | `dire_team_id` |
| `nextMatchId` | `next_game` (FK resolved in pass 2) |
| `nextMatchSlot` | `next_game_slot` |
| `loserNextMatchId` | `loser_next_game` (FK resolved in pass 2) |
| `loserNextMatchSlot` | `loser_next_game_slot` |
| `status` | `status` |

### Advance Winner (Update)

```
POST /bracket/games/{game_id}/advance/
Body: { "winner": "radiant" | "dire" }
```

**Updated flow:**

1. Set `game.winning_team` and `game.status = 'completed'`
2. Advance winner to `next_game` if exists (existing logic)
3. Check if loser has `loser_next_game`:
   - YES: Advance loser to losers bracket (existing logic)
   - NO: Calculate and set `losing_team.placement`
4. If grand finals: Also set `winning_team.placement = 1`
5. Return updated game

### Manual Placement Override (New)

```
PATCH /api/tournaments/{tournament_id}/teams/{team_id}/placement/
Body: { "placement": 3 }
```

Allows admin to correct auto-calculated placements for forfeits, disqualifications, tiebreakers.

## Placement Calculation

### Double Elimination Logic

| Eliminated From | Placement |
|-----------------|-----------|
| Grand Finals (loser) | 2nd |
| Losers Finals | 3rd |
| Losers Semi | 4th (tied) |
| Losers Round N-1 | 5th-6th (tied) |
| Losers Round N-2 | 7th-8th (tied) |

### Algorithm

```python
def calculate_placement(game, losing_team):
    """Calculate placement for eliminated team."""

    # Grand finals loser = 2nd place
    if game.bracket_type == 'grand_finals':
        return 2

    # Losers bracket elimination
    if game.bracket_type == 'losers':
        total_losers_rounds = Game.objects.filter(
            tournament=game.tournament,
            bracket_type='losers'
        ).aggregate(Max('round'))['round__max']

        rounds_from_final = total_losers_rounds - game.round

        if rounds_from_final == 0:  # Losers finals
            return 3
        else:
            # Each earlier round doubles the tied placement range
            base = 4
            for i in range(rounds_from_final - 1):
                base += 2 ** i
            return base

    # Winners bracket elimination → goes to losers (no placement yet)
    return None
```

## Frontend Changes

Minimal changes required:
- Update `gameId` fields after save response so subsequent operations use correct PKs
- Existing `bracketStore.saveBracket()` already sends correct data format

## Files to Modify

### Backend

- `backend/app/models.py` - Add `placement` field to Team
- `backend/app/views/bracket.py` - Implement `save_bracket`, update `advance_winner`
- `backend/app/serializers.py` - Update serializers if needed
- `backend/app/urls.py` or `backend/bracket/urls.py` - Add placement override endpoint

### Migrations

- New migration for Team.placement field

### Tests

- Test save_bracket creates correct Game records
- Test advance_winner sets placement on elimination
- Test placement calculation for various bracket positions
- Test manual placement override

## Future Considerations

This design enables future work:
- Player MMR adjustments based on team placement
- Leaderboard integration with tournament results
- Historical placement tracking across tournaments
