# Shuffle Draft UI Redesign

## Overview

Redesign the shuffle draft UI to provide better visibility into pick order, team MMRs, and double pick opportunities. Also fix bugs with auto-advancing to the next round after picks.

## Requirements

1. **Bug Fix**: Shuffle draft not advancing to next step after a pick
2. **Architecture Change**: Create all 16 rounds upfront (like snake/normal), but captain is null until previous round completes
3. **UI Changes (shuffle draft only)**:
   - Replace large captain cards with simple pick order list
   - Add dedicated "opponent MMR" callout showing threshold for double pick
   - In player table: show projected MMR and pick order for each player
   - In player table: highlight in green rows where picking guarantees a double pick
4. **Refresh Behavior**: Always refresh state, but only auto-advance when "Auto Advance" is enabled

## Architecture Changes

### Round Creation (Backend)

All 16 rounds created upfront when draft initializes, but for shuffle draft:
- `captain` field starts as `null`
- After each pick, recalculate team MMRs and assign the captain for the next incomplete round
- `latest_round` points to the first round where `captain` is assigned but `choice` is null

## Backend Changes

### New file: `backend/app/functions/shuffle_draft.py`

All shuffle-specific logic in one place:

```python
"""Shuffle draft logic - lowest MMR picks first."""
import random
from typing import Optional

def get_team_total_mmr(team) -> int:
    """Calculate total MMR for a team (captain + members)."""
    total = team.captain.mmr or 0 if team.captain else 0
    for member in team.members.exclude(id=team.captain_id):
        total += member.mmr or 0
    return total


def roll_until_winner(teams: list) -> tuple:
    """Roll dice until one winner. Returns (winner, roll_rounds)."""
    roll_rounds = []
    remaining = list(teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [t for t in remaining
                     if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll]

    return remaining[0], roll_rounds


def get_lowest_mmr_team(teams: list) -> tuple:
    """
    Find team with lowest total MMR.
    Returns (team, tie_resolution_data or None).
    """
    team_mmrs = [(team, get_team_total_mmr(team)) for team in teams]
    min_mmr = min(mmr for _, mmr in team_mmrs)
    tied = [t for t, mmr in team_mmrs if mmr == min_mmr]

    if len(tied) > 1:
        winner, roll_rounds = roll_until_winner(tied)
        tie_data = {
            "tied_teams": [{"id": t.id, "name": t.name, "mmr": get_team_total_mmr(t)} for t in tied],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id,
        }
        return winner, tie_data

    return tied[0], None


def build_shuffle_rounds(draft) -> None:
    """Create all rounds for shuffle draft, assign first captain."""
    from app.models import DraftRound

    teams = list(draft.tournament.teams.all())
    num_teams = len(teams)
    total_picks = num_teams * 4

    # Create all rounds with null captains
    rounds = [
        DraftRound(
            draft=draft,
            captain=None,
            pick_number=i,
            pick_phase=(i - 1) // num_teams + 1,
        )
        for i in range(1, total_picks + 1)
    ]
    DraftRound.objects.bulk_create(rounds)

    # Assign first captain (use captain MMR only for first pick)
    first_team, tie_data = get_lowest_mmr_team(teams)
    first_round = draft.draft_rounds.first()
    first_round.captain = first_team.captain
    if tie_data:
        first_round.was_tie = True
        first_round.tie_roll_data = tie_data
    first_round.save()


def assign_next_shuffle_captain(draft) -> Optional[dict]:
    """
    After a pick, assign captain to next round.
    Returns tie_resolution data if tie occurred, else None.
    """
    next_round = draft.draft_rounds.filter(captain__isnull=True).first()
    if not next_round:
        return None

    teams = list(draft.tournament.teams.all())
    next_team, tie_data = get_lowest_mmr_team(teams)

    next_round.captain = next_team.captain
    if tie_data:
        next_round.was_tie = True
        next_round.tie_roll_data = tie_data
    next_round.save()

    return tie_data
```

### Model Changes (`backend/app/models.py`)

Clean delegation to shuffle module:

```python
def build_rounds(self):
    self.draft_rounds.all().delete()

    if self.draft_style == "shuffle":
        from app.functions.shuffle_draft import build_shuffle_rounds
        build_shuffle_rounds(self)
        return

    # ... existing snake/normal logic unchanged ...
```

### View Changes (`backend/app/functions/tournament.py`)

```python
# After successful pick
if draft.draft_style == 'shuffle' and draft.users_remaining.exists():
    from app.functions.shuffle_draft import assign_next_shuffle_captain
    tie_data = assign_next_shuffle_captain(draft)
    if tie_data:
        response_data["tie_resolution"] = tie_data
```

## Frontend Changes

### 1. New Hook: `useShuffleRefresh.ts`

```typescript
import { useEffect } from 'react';
import { useUserStore } from '~/store/userStore';
import { refreshDraftHook } from './refreshDraftHook';
import { refreshTournamentHook } from './refreshTournamentHook';
import type { DraftRoundType, DraftType } from '../types';

interface UseShuffleRefreshOptions {
  autoAdvance: boolean;
  interval?: number;
}

export function useShuffleRefresh({ autoAdvance, interval = 3000 }: UseShuffleRefreshOptions) {
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);

  const refresh = async () => {
    await refreshDraftHook({ draft, setDraft });
    await refreshTournamentHook({ tournament, setTournament });
  };

  const advanceToLatest = (updatedDraft: DraftType) => {
    const latestRound = updatedDraft.draft_rounds?.find(
      (r: DraftRoundType) => r.captain && !r.choice
    );
    if (latestRound) {
      setCurDraftRound(latestRound);
      const idx = updatedDraft.draft_rounds?.findIndex(
        (r: DraftRoundType) => r.pk === latestRound.pk
      );
      if (idx !== undefined && idx >= 0) {
        setDraftIndex(idx);
      }
    }
  };

  // Always refresh on interval, only auto-advance when enabled
  useEffect(() => {
    const timer = setInterval(async () => {
      await refresh();
      if (autoAdvance) {
        advanceToLatest(draft);
      }
    }, interval);

    return () => clearInterval(timer);
  }, [draft?.pk, autoAdvance, interval]);

  return { refresh, advanceToLatest };
}
```

### 2. Rename "Live Reload" to "Auto Advance"

In `tournamentStore.ts`:
```typescript
// Rename state
liveReload: boolean  ->  autoAdvance: boolean
setLiveReload()      ->  setAutoAdvance()
```

In UI toggle button:
```tsx
<Button
  variant={autoAdvance ? "default" : "outline"}
  onClick={() => setAutoAdvance(!autoAdvance)}
>
  Auto Advance: {autoAdvance ? 'ON' : 'OFF'}
</Button>
```

### 3. Update `choosePlayerHook.tsx`

After successful pick, advance to next round:

```typescript
success: (data) => {
  setTournament(data);
  setDraft(data.draft);

  // Always advance to next round after YOUR pick
  const nextRound = data.draft.draft_rounds?.find(
    (r: DraftRoundType) => r.captain && !r.choice
  );

  if (nextRound) {
    setCurDraftRound(nextRound);
    const idx = data.draft.draft_rounds?.findIndex(
      (r: DraftRoundType) => r.pk === nextRound.pk
    );
    if (idx !== undefined && idx >= 0) {
      setDraftIndex(idx);
    }
  }

  // Handle tie overlay
  if (data.draft?.draft_style === 'shuffle' && data.tie_resolution) {
    onTieResolution?.(data.tie_resolution);
  }

  return `Pick ${curDraftRound?.pick_number} complete!`;
}
```

### 4. New Component: `ShufflePickOrder.tsx`

**File: `frontend/app/components/draft/shuffle/ShufflePickOrder.tsx`**

Compact horizontal list showing pick order:

```
+-------------------------------------------------------------+
|  Pick Order                                                 |
|  +--------------+ +--------------+ +--------------+         |
|  | Team Alpha   | | Team Beta    | | Team Gamma   |   ...   |
|  | 12,400 MMR   | | 12,800 MMR   | | 13,100 MMR   |         |
|  | 2 picks - v1 | | 2 picks - =  | | 3 picks - ^1 |         |
|  |   PICKING    | +--------------+ +--------------+         |
|  +--------------+                                           |
+-------------------------------------------------------------+
```

Each card shows:
- Team name
- Current total MMR
- Total picks made (e.g., "2 picks")
- Position indicator: v1 = 1 pick behind, ^1 = 1 pick ahead, = = even
- Current picker highlighted with "PICKING" badge and accent border

```tsx
import { cn } from '~/lib/utils';
import { Badge } from '~/components/ui/badge';
import { Card } from '~/components/ui/card';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

interface TeamPickStatus {
  team: TeamType;
  totalMmr: number;
  picksMade: number;
  pickOrder: number;
}

export const ShufflePickOrder: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

  const getTeamPickStatus = (): TeamPickStatus[] => {
    const teams = tournament?.teams || [];

    const statuses = teams.map((team) => {
      let totalMmr = team.captain?.mmr || 0;
      team.members?.forEach((member) => {
        if (member.pk !== team.captain?.pk) {
          totalMmr += member.mmr || 0;
        }
      });

      const picksMade = draft?.draft_rounds?.filter(
        (r) => r.choice && r.captain?.pk === team.captain?.pk
      ).length || 0;

      return { team, totalMmr, picksMade, pickOrder: 0 };
    });

    statuses.sort((a, b) => a.totalMmr - b.totalMmr);
    statuses.forEach((s, idx) => {
      s.pickOrder = idx + 1;
    });

    return statuses;
  };

  const getPickDelta = (picksMade: number, allStatuses: TeamPickStatus[]): string => {
    const avgPicks = allStatuses.reduce((sum, s) => sum + s.picksMade, 0) / allStatuses.length;
    const delta = picksMade - avgPicks;

    if (delta > 0.5) return `^${Math.round(delta)}`;
    if (delta < -0.5) return `v${Math.abs(Math.round(delta))}`;
    return '=';
  };

  const isCurrentPicker = (team: TeamType): boolean => {
    return curDraftRound?.captain?.pk === team.captain?.pk;
  };

  const statuses = getTeamPickStatus();

  return (
    <div className="mb-4">
      <h3 className="text-sm font-medium text-muted-foreground mb-2">
        Pick Order
      </h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {statuses.map((status) => (
          <Card
            key={status.team.pk}
            className={cn(
              'flex-shrink-0 p-3 min-w-[140px]',
              isCurrentPicker(status.team)
                ? 'border-green-500 border-2 bg-green-950/20'
                : 'border-muted'
            )}
          >
            <div className="flex flex-col gap-1">
              <span className="font-medium text-sm truncate">
                {status.team.name}
              </span>

              <span className="text-xs text-muted-foreground">
                {status.totalMmr.toLocaleString()} MMR
              </span>

              <div className="flex items-center gap-2 text-xs">
                <span>{status.picksMade} picks</span>
                <span className={cn(
                  getPickDelta(status.picksMade, statuses).startsWith('v')
                    ? 'text-red-400'
                    : getPickDelta(status.picksMade, statuses).startsWith('^')
                    ? 'text-green-400'
                    : 'text-muted-foreground'
                )}>
                  {getPickDelta(status.picksMade, statuses)}
                </span>
              </div>

              {isCurrentPicker(status.team) && (
                <Badge variant="default" className="mt-1 bg-green-600 text-xs">
                  PICKING
                </Badge>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};
```

### 5. New Component: `DoublePickThreshold.tsx`

**File: `frontend/app/components/draft/shuffle/DoublePickThreshold.tsx`**

Callout showing the MMR threshold for double pick:

```
+-------------------------------------------------------------+
|  * Double Pick Threshold                                    |
|  Stay under 12,800 MMR to pick again (Team Beta)            |
|  Your current MMR: 12,400 (400 buffer)                      |
+-------------------------------------------------------------+
```

```tsx
import { Zap } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

export const DoublePickThreshold: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const user = useUserStore((state) => state.user);
  const isStaff = useUserStore((state) => state.isStaff);

  if (draft?.draft_style !== 'shuffle') return null;

  const isCurrentPicker = curDraftRound?.captain?.pk === user?.pk;
  if (!isCurrentPicker && !isStaff()) return null;

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curDraftRound?.captain?.pk
    );
  };

  const getThresholdTeam = (): { team: TeamType; mmr: number } | null => {
    const teams = tournament?.teams || [];
    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    const otherTeams = teams
      .filter((t) => t.pk !== currentTeam.pk)
      .map((t) => ({ team: t, mmr: getTeamMmr(t) }))
      .sort((a, b) => a.mmr - b.mmr);

    return otherTeams[0] || null;
  };

  const currentTeam = getCurrentTeam();
  const threshold = getThresholdTeam();

  if (!currentTeam || !threshold) return null;

  const currentMmr = getTeamMmr(currentTeam);
  const canDoublePick = currentMmr < threshold.mmr;

  return (
    <Alert
      className={cn(
        'mb-4',
        canDoublePick
          ? 'border-green-500 bg-green-950/20'
          : 'border-muted'
      )}
    >
      <Zap className={cn(
        'h-4 w-4',
        canDoublePick ? 'text-green-500' : 'text-muted-foreground'
      )} />
      <AlertTitle className="text-sm font-medium">
        Double Pick Threshold
      </AlertTitle>
      <AlertDescription className="text-sm">
        <div className="flex flex-col gap-1 mt-1">
          <span>
            Stay under{' '}
            <span className="font-semibold">
              {threshold.mmr.toLocaleString()} MMR
            </span>
            {' '}to pick again
            <span className="text-muted-foreground">
              {' '}({threshold.team.name})
            </span>
          </span>
          <span className="text-muted-foreground">
            Your current MMR:{' '}
            <span className={cn(
              'font-medium',
              canDoublePick ? 'text-green-400' : 'text-foreground'
            )}>
              {currentMmr.toLocaleString()}
            </span>
            {canDoublePick && (
              <span className="text-green-400 ml-2">
                ({(threshold.mmr - currentMmr).toLocaleString()} buffer)
              </span>
            )}
          </span>
        </div>
      </AlertDescription>
    </Alert>
  );
};
```

### 6. Update `draftTable.tsx` - Projected Column

Add projected MMR and pick order column, with green row highlighting:

```tsx
import { Suspense, useMemo } from 'react';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import type { UserType } from '~/components/user/types';
import type { TeamType } from '~/index';
import { AvatarUrl } from '~/index';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from '../../user/positions';
import { ChoosePlayerButton } from '../buttons/choosePlayerButtons';

export const DraftTable: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const curRound = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);

  const isShuffle = draft?.draft_style === 'shuffle';

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curRound?.captain?.pk
    );
  };

  const teamMmrs = useMemo(() => {
    if (!isShuffle) return [];
    return (tournament?.teams || []).map((t) => ({
      team: t,
      mmr: getTeamMmr(t),
    }));
  }, [tournament?.teams, isShuffle]);

  const currentTeam = getCurrentTeam();
  const currentTeamMmr = currentTeam ? getTeamMmr(currentTeam) : 0;

  const getProjectedData = (playerMmr: number) => {
    if (!isShuffle || !currentTeam) return null;

    const projectedMmr = currentTeamMmr + playerMmr;

    const projectedTeamMmrs = teamMmrs.map((t) =>
      t.team.pk === currentTeam.pk
        ? { ...t, mmr: projectedMmr }
        : t
    );

    projectedTeamMmrs.sort((a, b) => a.mmr - b.mmr);
    const pickOrder = projectedTeamMmrs.findIndex(
      (t) => t.team.pk === currentTeam.pk
    ) + 1;

    return {
      projectedMmr,
      pickOrder,
      isDoublePick: pickOrder === 1,
    };
  };

  const members = () => {
    const a = tournament?.draft?.users_remaining?.sort(
      (a: UserType, b: UserType) => {
        if (!a.mmr && !b.mmr) return 0;
        if (!a.mmr) return 1;
        if (!b.mmr) return -1;
        if (a.mmr === b.mmr) {
          return (a.username || '').localeCompare(b.username || '');
        }
        return a.mmr >= b.mmr ? -1 : 1;
      }
    );
    return a || [];
  };

  const getOrdinal = (n: number): string => {
    const s = ['th', 'st', 'nd', 'rd'];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };

  return (
    <Suspense>
      <Table>
        <TableCaption>Tournament Users</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead>MMR</TableHead>
            {isShuffle && <TableHead>Projected</TableHead>}
            <TableHead className="hidden md:table-cell">Positions</TableHead>
            <TableHead>Choose?</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members().map((user: UserType) => {
            const projected = getProjectedData(user.mmr || 0);

            return (
              <TableRow
                key={`TeamTableRow-${user.pk}`}
                className={cn(
                  projected?.isDoublePick && 'bg-green-950/30'
                )}
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="avatar w-8 h-8">
                      <img
                        src={AvatarUrl(user)}
                        alt={user.username}
                        className="rounded-full"
                      />
                    </span>
                    <span>{user.nickname || user.username}</span>
                  </div>
                </TableCell>

                <TableCell>{user.mmr ?? 'N/A'}</TableCell>

                {isShuffle && (
                  <TableCell>
                    {projected ? (
                      <div className="flex flex-col">
                        <span className="text-sm">
                          {projected.projectedMmr.toLocaleString()}
                        </span>
                        <span
                          className={cn(
                            'text-xs font-medium',
                            projected.isDoublePick
                              ? 'text-green-400'
                              : 'text-muted-foreground'
                          )}
                        >
                          {getOrdinal(projected.pickOrder)}
                          {projected.isDoublePick && ' \u2713'}
                        </span>
                      </div>
                    ) : (
                      '-'
                    )}
                  </TableCell>
                )}

                <TableCell className="hidden md:table-cell">
                  <RolePositions user={user} />
                </TableCell>

                <TableCell>
                  <ChoosePlayerButton user={user} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Suspense>
  );
};
```

### 7. Update `DraftRoundView.tsx`

Conditionally render ShufflePickOrder vs CaptainCards:

```tsx
import { ShufflePickOrder } from './shuffle/ShufflePickOrder';

// In the render:
return (
  <>
    {draft.draft_style === 'shuffle' ? (
      <ShufflePickOrder />
    ) : (
      <CaptainCards />
    )}
    <div className="p-4">
      {/* ... rest unchanged ... */}
    </div>
  </>
);
```

### 8. Update `PlayerChoiceView.tsx`

Add DoublePickThreshold above table:

```tsx
import { DoublePickThreshold } from '../shuffle/DoublePickThreshold';

return (
  <div>
    <DoublePickThreshold />
    <DraftTable />
  </div>
);
```

## File Changes Summary

### Backend (New/Modified)

| File | Change |
|------|--------|
| `backend/app/functions/shuffle_draft.py` | **New** - All shuffle draft logic |
| `backend/app/models.py` | Modify `build_rounds()` to delegate to shuffle module |
| `backend/app/functions/tournament.py` | Call `assign_next_shuffle_captain()` after pick |

### Frontend (New/Modified)

| File | Change |
|------|--------|
| `frontend/app/components/draft/shuffle/ShufflePickOrder.tsx` | **New** - Pick order list component |
| `frontend/app/components/draft/shuffle/DoublePickThreshold.tsx` | **New** - Threshold callout component |
| `frontend/app/components/draft/hooks/useShuffleRefresh.ts` | **New** - Refresh/auto-advance hook |
| `frontend/app/components/draft/roundView/draftTable.tsx` | Add projected column, green highlighting |
| `frontend/app/components/draft/draftRoundView.tsx` | Conditional ShufflePickOrder vs CaptainCards |
| `frontend/app/components/draft/roundView/choiceCard.tsx` | Add DoublePickThreshold |
| `frontend/app/components/draft/hooks/choosePlayerHook.tsx` | Auto-advance after pick |
| `frontend/app/store/tournamentStore.ts` | Rename liveReload to autoAdvance |
| `frontend/app/components/draft/draftModal.tsx` | Update toggle button text |

## Testing Considerations

1. **Unit tests for shuffle_draft.py**:
   - `get_team_total_mmr()` calculates correctly
   - `roll_until_winner()` always returns one winner
   - `get_lowest_mmr_team()` handles ties
   - `build_shuffle_rounds()` creates correct number of rounds

2. **Integration tests**:
   - Full shuffle draft flow with multiple picks
   - Captain assignment after each pick
   - Tie resolution triggers correctly

3. **Frontend tests**:
   - Projected column shows correct values
   - Green highlighting appears for double pick rows
   - Auto-advance moves to next round
   - ShufflePickOrder shows correct pick order

4. **Edge cases**:
   - All teams have same MMR at start
   - Multiple re-rolls needed (all teams roll same value)
   - Last pick (no next round to assign)
   - Draft with only 2 teams vs 4 teams
