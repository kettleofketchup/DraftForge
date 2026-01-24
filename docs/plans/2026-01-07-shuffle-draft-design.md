# Shuffle Draft Design

**Status:** Completed

## Overview

Add a new "Shuffle Draft" style where the team with the lowest total MMR always picks first. After each pick, team MMRs are recalculated and pick order is re-determined. Ties are resolved with dice rolls.

## Requirements

1. **Lowest MMR picks first** - After each pick, calculate total team MMR (captain + members) and the lowest picks next
2. **Tie-breaking with dice rolls** - When teams have equal MMR, each rolls a d6; highest wins. Re-roll on ties until one winner
3. **Visual tie display** - Show an overlay with roll results when ties occur
4. **Team `total_mmr` helper** - Add computed field to team serializer

## Core Logic

### How Shuffle Draft Differs from Snake/Normal

| Aspect | Snake/Normal | Shuffle |
|--------|--------------|---------|
| Pick order | Predetermined at draft start | Recalculated after each pick |
| DraftRounds | All created upfront via `build_rounds()` | Created one-at-a-time after each pick |
| Predictable | Yes - can simulate final team MMRs | No - depends on captain choices |

### MMR Calculation

Total team MMR = captain MMR + sum of all picked member MMRs

```python
def get_team_total_mmr(team):
    total = team.captain.mmr or 0
    for member in team.members.exclude(id=team.captain_id):
        total += member.mmr or 0
    return total
```

### Tie-Breaking Roll Mechanic

1. Each tied team rolls a d6 (1-6)
2. Highest roll wins and picks next
3. If rolls tie, re-roll only among still-tied teams until one winner

**Example with 3 tied teams:**
```
Team A (15,400 MMR) rolls: 4
Team B (15,400 MMR) rolls: 4
Team C (15,400 MMR) rolls: 2

→ Team A and B still tied, Team C eliminated
→ Re-roll:
   Team A rolls: 3
   Team B rolls: 5

→ Team B wins, picks next
```

## Backend Changes

### 1. Model Changes (`backend/app/models.py`)

**Add `shuffle` to DraftStyles:**
```python
class DraftStyles(StrEnum):
    snake = "snake"
    normal = "normal"
    shuffle = "shuffle"
```

**Update Draft.DRAFT_STYLE_CHOICES:**
```python
DRAFT_STYLE_CHOICES = [
    ("snake", "Snake"),
    ("normal", "Normal"),
    ("shuffle", "Shuffle"),
]
```

**Add fields to DraftRound for tie tracking:**
```python
class DraftRound(models.Model):
    # ... existing fields ...
    was_tie = models.BooleanField(default=False)
    tie_roll_data = models.JSONField(null=True, blank=True)
    # Stores: {"tied_teams": [...], "roll_rounds": [...], "winner_id": N}
```

**New method `Draft.roll_until_winner()`:**
```python
def roll_until_winner(self, tied_teams):
    """Roll until exactly one winner. Returns (winner_team, roll_rounds)."""
    import random

    roll_rounds = []
    remaining = list(tied_teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [t for t in remaining
                     if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll]

    return remaining[0], roll_rounds
```

**New method `Draft.create_next_shuffle_round()`:**
```python
def create_next_shuffle_round(self):
    """
    Calculate which team picks next based on lowest total MMR.
    Returns dict with round, team_mmr, and tie_resolution if applicable.
    """
    teams = list(self.tournament.teams.all())

    # Calculate current MMR for each team
    team_mmrs = []
    for team in teams:
        total = (team.captain.mmr or 0)
        for member in team.members.exclude(id=team.captain_id):
            total += (member.mmr or 0)
        team_mmrs.append({"team": team, "mmr": total})

    # Find lowest MMR
    min_mmr = min(t["mmr"] for t in team_mmrs)
    tied_teams = [t for t in team_mmrs if t["mmr"] == min_mmr]

    # Handle tie with random rolls
    tie_resolution = None
    if len(tied_teams) > 1:
        winner, roll_rounds = self.roll_until_winner([t["team"] for t in tied_teams])
        tie_resolution = {
            "tied_teams": [{"id": t["team"].id, "name": t["team"].name, "mmr": t["mmr"]}
                          for t in tied_teams],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id
        }
        next_team = winner
        next_mmr = next(t["mmr"] for t in tied_teams if t["team"].id == winner.id)
    else:
        next_team = tied_teams[0]["team"]
        next_mmr = tied_teams[0]["mmr"]

    # Create the DraftRound
    pick_number = self.draft_rounds.count() + 1
    num_teams = len(teams)
    phase = (pick_number - 1) // num_teams + 1

    draft_round = DraftRound.objects.create(
        draft=self,
        captain=next_team.captain,
        pick_number=pick_number,
        pick_phase=phase,
        was_tie=bool(tie_resolution),
        tie_roll_data=tie_resolution
    )

    return {
        "round": draft_round,
        "team_mmr": next_mmr,
        "tie_resolution": tie_resolution
    }
```

**Modify `Draft.build_rounds()` for shuffle:**
```python
def build_rounds(self):
    # ... existing code for clearing rounds ...

    if self.draft_style == "shuffle":
        # For shuffle, only create the first round based on captain MMRs
        teams = list(self.tournament.teams.all())
        team_mmrs = [(t, t.captain.mmr or 0) for t in teams]

        # Find lowest captain MMR for first pick
        min_mmr = min(mmr for _, mmr in team_mmrs)
        tied_teams = [t for t, mmr in team_mmrs if mmr == min_mmr]

        if len(tied_teams) > 1:
            winner, roll_rounds = self.roll_until_winner(tied_teams)
            tie_resolution = {
                "tied_teams": [{"id": t.id, "name": t.name, "mmr": t.captain.mmr or 0}
                              for t in tied_teams],
                "roll_rounds": roll_rounds,
                "winner_id": winner.id
            }
            first_team = winner
        else:
            first_team = tied_teams[0]
            tie_resolution = None

        DraftRound.objects.create(
            draft=self,
            captain=first_team.captain,
            pick_number=1,
            pick_phase=1,
            was_tie=bool(tie_resolution),
            tie_roll_data=tie_resolution
        )
        return

    # ... existing snake/normal logic ...
```

### 2. Serializer Changes (`backend/app/serializers.py`)

**Add `total_mmr` to TeamSerializer:**
```python
class TeamSerializer(serializers.ModelSerializer):
    total_mmr = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [..., 'total_mmr']

    def get_total_mmr(self, obj):
        """Sum of captain MMR + all member MMRs."""
        total = 0
        if obj.captain and obj.captain.mmr:
            total += obj.captain.mmr
        for member in obj.members.all():
            if member.mmr and member.pk != obj.captain_id:
                total += member.mmr
        return total
```

### 3. View Changes (`backend/app/views.py`)

**Update pick endpoint for shuffle draft:**
```python
@api_view(['POST'])
def pick_player(request, draft_id):
    draft = get_object_or_404(Draft, pk=draft_id)
    player_id = request.data.get('player_id')
    player = get_object_or_404(CustomUser, pk=player_id)

    # Get current round and make pick
    current_round = draft.draft_rounds.filter(choice__isnull=True).order_by('pick_number').first()
    current_round.pick_player(player)

    response_data = {
        "success": True,
        "pick": {
            "round_id": current_round.pk,
            "player_id": player.pk,
            "team_id": current_round.team.pk
        }
    }

    # For shuffle draft, create next round dynamically
    if draft.draft_style == 'shuffle' and draft.users_remaining.exists():
        next_pick_data = draft.create_next_shuffle_round()
        response_data["next_pick"] = {
            "captain_id": next_pick_data["round"].captain.pk,
            "team_id": next_pick_data["round"].team.pk,
            "team_name": next_pick_data["round"].team.name,
            "team_mmr": next_pick_data["team_mmr"]
        }
        if next_pick_data.get("tie_resolution"):
            response_data["tie_resolution"] = next_pick_data["tie_resolution"]

    return Response(response_data)
```

### 4. Migration

New migration for DraftRound fields:
- `was_tie` (BooleanField, default=False)
- `tie_roll_data` (JSONField, null=True, blank=True)

## Frontend Changes

### 1. Type Updates (`frontend/app/components/draft/types.d.ts`)

```typescript
// Update draft_style type
export interface DraftType {
  pk: number;
  draft_style: 'snake' | 'normal' | 'shuffle';
  // ... other fields
}

// Add TieResolution type
export interface TieResolution {
  tied_teams: Array<{
    id: number;
    name: string;
    mmr: number;
  }>;
  roll_rounds: Array<Array<{
    team_id: number;
    roll: number;
  }>>;
  winner_id: number;
}

// Add to pick response
export interface PickResponse {
  success: boolean;
  pick: {
    round_id: number;
    player_id: number;
    team_id: number;
  };
  next_pick?: {
    captain_id: number;
    team_id: number;
    team_name: string;
    team_mmr: number;
  };
  tie_resolution?: TieResolution;
}
```

### 2. Draft Style Modal (`frontend/app/components/draft/buttons/draftStyleModal.tsx`)

**Add Shuffle option to Select:**
```tsx
<SelectItem value="shuffle">
  <div className="flex flex-col">
    <span className="font-medium">Shuffle Draft</span>
    <span className="text-xs text-muted-foreground">
      Lowest MMR team picks first, recalculated each round
    </span>
  </div>
</SelectItem>
```

**Add Shuffle stats display:**
```tsx
{/* Shuffle Draft Stats */}
<div className="rounded-lg border p-4 space-y-2">
  <div className="flex items-center justify-between">
    <h4 className="font-medium text-purple-600">Shuffle Draft</h4>
    <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
      Dynamic balance
    </span>
  </div>
  <p className="text-sm text-muted-foreground">
    Pick order adjusts after each selection to favor the lowest MMR team.
    Cannot predict final balance - depends on captain choices.
  </p>
</div>
```

**Update selectedStyle type:**
```tsx
const [selectedStyle, setSelectedStyle] = useState<'snake' | 'normal' | 'shuffle'>(
  draft?.draft_style || 'snake',
);
```

### 3. New Component: TieResolutionOverlay (`frontend/app/components/draft/TieResolutionOverlay.tsx`)

```tsx
import React from 'react';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import type { TieResolution } from './types';

interface TieResolutionOverlayProps {
  tieResolution: TieResolution;
  onDismiss: () => void;
}

export const TieResolutionOverlay: React.FC<TieResolutionOverlayProps> = ({
  tieResolution,
  onDismiss,
}) => {
  const { tied_teams, roll_rounds, winner_id } = tieResolution;
  const winner = tied_teams.find((t) => t.id === winner_id);

  return (
    <Dialog open={true} onOpenChange={onDismiss}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-center text-xl">
            Tie Breaker!
          </DialogTitle>
        </DialogHeader>

        {/* Team headers */}
        <div className="grid grid-cols-2 gap-4 text-center">
          {tied_teams.map((team) => (
            <div
              key={team.id}
              className={team.id === winner_id ? 'font-bold' : ''}
            >
              <div>{team.name}</div>
              <div className="text-sm text-muted-foreground">
                {team.mmr.toLocaleString()} MMR
              </div>
            </div>
          ))}
        </div>

        {/* Roll rounds */}
        <div className="space-y-2 mt-4">
          {roll_rounds.map((round, roundIdx) => (
            <div
              key={roundIdx}
              className="grid grid-cols-[auto,1fr] gap-2 items-center"
            >
              <span className="text-sm text-muted-foreground">
                Round {roundIdx + 1}:
              </span>
              <div className="grid grid-cols-2 gap-4 text-center">
                {tied_teams.map((team) => {
                  const roll = round.find((r) => r.team_id === team.id);
                  if (!roll) return <span key={team.id}>-</span>;

                  const isLastRound = roundIdx === roll_rounds.length - 1;
                  const isWinner = isLastRound && roll.team_id === winner_id;

                  return (
                    <span
                      key={roll.team_id}
                      className={isWinner ? 'text-green-600 font-bold' : ''}
                    >
                      {roll.roll} {isWinner && '✓'}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Winner announcement */}
        <div className="text-center mt-4 p-3 bg-green-50 dark:bg-green-950/20 rounded-lg">
          <span className="text-green-700 dark:text-green-300 font-medium">
            {winner?.name} picks next!
          </span>
        </div>

        <DialogFooter>
          <Button onClick={onDismiss} className="w-full">
            Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

### 4. Integration (`frontend/app/components/draft/hooks/choosePlayerHook.tsx`)

**Add state for tie resolution:**
```tsx
const [tieResolution, setTieResolution] = useState<TieResolution | null>(null);
const [showTieOverlay, setShowTieOverlay] = useState(false);
```

**Update pick handler:**
```tsx
const handlePick = async (playerId: number) => {
  const response = await api.post<PickResponse>(`/draft/${draft.pk}/pick/`, {
    player_id: playerId,
  });

  if (response.data.success) {
    refreshDraft();

    // Show tie overlay for shuffle draft
    if (draft.draft_style === 'shuffle' && response.data.tie_resolution) {
      setTieResolution(response.data.tie_resolution);
      setShowTieOverlay(true);
    }
  }
};
```

**Render overlay:**
```tsx
{showTieOverlay && tieResolution && (
  <TieResolutionOverlay
    tieResolution={tieResolution}
    onDismiss={() => {
      setShowTieOverlay(false);
      setTieResolution(null);
    }}
  />
)}
```

## File Changes Summary

### Backend

| File | Changes |
|------|---------|
| `backend/app/models.py` | Add `shuffle` to `DraftStyles`, add `was_tie`/`tie_roll_data` to `DraftRound`, add `create_next_shuffle_round()` and `roll_until_winner()` methods, update `build_rounds()` |
| `backend/app/serializers.py` | Add `total_mmr` computed field to `TeamSerializer` |
| `backend/app/views.py` | Update pick endpoint to handle shuffle draft flow and return `tie_resolution` |
| `backend/app/migrations/` | New migration for `DraftRound.was_tie` and `DraftRound.tie_roll_data` |

### Frontend

| File | Changes |
|------|---------|
| `frontend/app/components/draft/types.d.ts` | Add `shuffle` to draft_style, add `TieResolution` and `PickResponse` types |
| `frontend/app/components/draft/buttons/draftStyleModal.tsx` | Add Shuffle option to dropdown, add shuffle stats display |
| `frontend/app/components/draft/hooks/choosePlayerHook.tsx` | Handle `tie_resolution` in response, show overlay |
| `frontend/app/components/draft/TieResolutionOverlay.tsx` | **New file** - tie resolution display component |

## Testing Considerations

1. **Unit tests for `roll_until_winner()`** - Verify it always returns exactly one winner
2. **Unit tests for `create_next_shuffle_round()`** - Verify correct team selected, tie handling
3. **Integration test** - Full shuffle draft flow with multiple picks
4. **Edge cases:**
   - All teams have same captain MMR at start
   - Multiple re-rolls needed (all teams roll same value)
   - Last pick (no next round needed)
