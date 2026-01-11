# Shuffle Draft Captain Assignment Fix

## Overview

Fix two related bugs in shuffle draft captain assignment:
- Issue #47: Double-picking on final pick assigns full team as next picker
- Issue #43: Undo doesn't reset the next round's captain

## Problem

### Issue #47: Full Teams Selected as Next Picker

In shuffle draft mode, when a captain makes their 4th and final pick (completing their team of 5), double-clicking can cause that same captain to be assigned as the next picker.

**Root Cause:** `assign_next_shuffle_captain` calls `get_lowest_mmr_team(teams)` without filtering out teams that have reached maximum capacity (5 members). Since the team that just picked likely still has the lowest MMR, they get selected again.

### Issue #43: Undo Doesn't Reset Next Captain

When undoing a pick in shuffle draft, the next round's captain assignment doesn't get recalculated.

**Root Cause:** `undo_last_pick` clears the choice but doesn't clear the next round's captain. In shuffle draft, after each pick, `assign_next_shuffle_captain` assigns a captain to the next round. When you undo, that assignment remains stale.

## Solution

### Fix 1: Filter Out Full Teams

Add `MAX_TEAM_SIZE = 5` constant and filter teams before finding lowest MMR in `assign_next_shuffle_captain`:

```python
# shuffle_draft.py
MAX_TEAM_SIZE = 5

def assign_next_shuffle_captain(draft) -> Optional[dict]:
    next_round = (
        draft.draft_rounds.filter(captain__isnull=True).order_by("pick_number").first()
    )
    if not next_round:
        return None

    teams = list(draft.tournament.teams.all())

    # Filter out teams that have reached max size
    eligible_teams = [t for t in teams if t.members.count() < MAX_TEAM_SIZE]

    if not eligible_teams:
        return None  # All teams full, draft complete

    next_team, tie_data = get_lowest_mmr_team(eligible_teams)
    # ... rest unchanged
```

### Fix 2: Clear Next Captain on Undo

In `undo_last_pick`, after clearing the choice, also clear the next round's captain:

```python
# tournament.py - in undo_last_pick()

# Clear the choice
last_round_with_choice.choice = None
last_round_with_choice.save()

# Clear the next round's captain so it gets recalculated
next_round = (
    draft.draft_rounds
    .filter(pick_number__gt=last_round_with_choice.pick_number)
    .order_by("pick_number")
    .first()
)
if next_round and next_round.choice is None:
    next_round.captain = None
    next_round.was_tie = False
    next_round.tie_roll_data = None
    next_round.save()
```

## Files to Change

| File | Change |
|------|--------|
| `backend/app/functions/shuffle_draft.py` | Add `MAX_TEAM_SIZE = 5`, filter eligible teams in `assign_next_shuffle_captain` |
| `backend/app/functions/tournament.py` | Clear next round's captain in `undo_last_pick` |

## Testing

1. **Issue #47 test**: Pick until a team has 5 members, verify that team is not assigned as next picker
2. **Issue #43 test**: Make a pick, undo it, verify next round's captain is cleared and recalculated on next pick
