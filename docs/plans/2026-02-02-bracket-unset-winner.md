# Bracket: Allow Unsetting Winner - Design

**Date:** 2026-02-02
**Issue:** https://github.com/kettleofketchup/DraftForge/issues/100
**Status:** Approved

## Problem

Currently, once a winner is set for a bracket game, there's no way to unset it. Users need the ability to undo/correct winner selections.

## Solution

Modify the `advance_winner` backend endpoint to accept `winner: null`, which will:
1. Clear the `winning_team` field
2. Reset game status to "scheduled"
3. Clear placement for the losing team (if any was set)
4. Leave downstream games as-is (teams remain assigned)

## API Design

**Endpoint:** `POST /api/bracket/games/<game_id>/advance-winner/`

**Request:**
```json
// Set winner
{"winner": "radiant"}

// Unset winner
{"winner": null}
```

**Behavior when `winner` is null:**
1. Find losing team before clearing (to reset their placement)
2. Clear `game.winning_team = None`
3. Reset `game.status = "scheduled"`
4. Clear `losing_team.placement = None` if it was set
5. Return updated game data

## Backend Implementation

**File:** `backend/app/views/bracket.py`

```python
def advance_winner(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    if not can_manage_game(request.user, game):
        return Response({"error": "..."}, status=403)

    winner = request.data.get("winner")

    # Handle unset case
    if winner is None:
        if game.winning_team:
            losing_team = game.dire_team if game.winning_team == game.radiant_team else game.radiant_team
            if losing_team and losing_team.placement:
                losing_team.placement = None
                losing_team.save()

        game.winning_team = None
        game.status = "scheduled"
        game.save()
        return Response(GameSerializer(game).data)

    # Existing set-winner logic...
```

## Frontend Implementation

### New file: `frontend/app/components/api/bracketAPI.tsx`

Move inline API calls from bracketStore to dedicated API file with Zod schemas:

```typescript
import { z } from 'zod';
import { api } from './axios';
import { BracketResponseSchema, type BracketResponse } from '~/components/bracket/schemas';
import type { BracketMatch } from '~/components/bracket/types';

export async function saveBracket(
  tournamentId: number,
  matches: BracketMatch[]
): Promise<BracketResponse> {
  const response = await api.post(`/bracket/tournaments/${tournamentId}/save/`, {
    matches,
  });
  return BracketResponseSchema.parse(response.data);
}

export async function loadBracket(tournamentId: number): Promise<BracketResponse> {
  const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
  return BracketResponseSchema.parse(response.data);
}
```

### Update: `frontend/app/store/bracketStore.ts`

1. Import from `bracketAPI.tsx` instead of inline `api` calls
2. Add `unsetMatchWinner` action:

```typescript
unsetMatchWinner: (matchId) => {
  const match = get().matches.find((m) => m.id === matchId);
  if (!match?.winner) return;

  const winningTeam = match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
  const losingTeam = match.winner === 'radiant' ? match.direTeam : match.radiantTeam;

  set((state) => ({
    matches: state.matches.map((m) => {
      if (m.id === matchId) {
        return { ...m, winner: undefined, status: 'pending' };
      }
      // Clear winning team from next match slot
      if (match.nextMatchId && m.id === match.nextMatchId) {
        const slot = match.nextMatchSlot;
        if (slot === 'radiant' && m.radiantTeam?.pk === winningTeam?.pk) {
          return { ...m, radiantTeam: undefined };
        }
        if (slot === 'dire' && m.direTeam?.pk === winningTeam?.pk) {
          return { ...m, direTeam: undefined };
        }
      }
      // Clear losing team from losers bracket slot
      if (match.loserNextMatchId && m.id === match.loserNextMatchId) {
        const slot = match.loserNextMatchSlot;
        if (slot === 'radiant' && m.radiantTeam?.pk === losingTeam?.pk) {
          return { ...m, radiantTeam: undefined };
        }
        if (slot === 'dire' && m.direTeam?.pk === losingTeam?.pk) {
          return { ...m, direTeam: undefined };
        }
      }
      return m;
    }),
    isDirty: true,
  }));
},
```

### Update: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

Add "Unset Winner" button when match has a winner:

```typescript
{isStaff && match.status === 'completed' && match.winner && (
  <div className="border-t pt-4">
    <Button
      variant="outline"
      onClick={() => unsetMatchWinner(match.id)}
      data-testid="unsetWinnerButton"
    >
      Unset Winner
    </Button>
  </div>
)}
```

## Test Plan

### Backend Test (Django)
- Test `advance_winner` with `winner: null`
- Verify winner cleared, status reset, placement cleared
- Add to CI pipeline

### Frontend Test (Playwright)
- Set winner → verify UI shows winner
- Unset winner → verify UI clears winner
- Save bracket → verify persistence
