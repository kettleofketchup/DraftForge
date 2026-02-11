# Shuffle Draft Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Shuffle Draft" mode where the team with the lowest total MMR always picks first, with dice-roll tie breaking.

**Architecture:** Shuffle draft differs from snake/normal by creating rounds dynamically after each pick. Backend calculates team MMRs, determines next picker, handles ties with random rolls. Frontend displays tie resolution overlay when ties occur.

**Tech Stack:** Django REST Framework (backend), React + TypeScript + shadcn/ui (frontend), existing Draft/DraftRound models

**Design Doc:** `docs/plans/2026-01-07-shuffle-draft-design.md`

---

## Task 1: Add Migration for DraftRound Tie Fields

**Files:**
- Modify: `backend/app/models.py:815-850` (DraftRound model)
- Create: `backend/app/migrations/XXXX_draftround_tie_fields.py` (auto-generated)

**Step 1: Add tie tracking fields to DraftRound model**

In `backend/app/models.py`, add fields after `choice` field in `DraftRound`:

```python
class DraftRound(models.Model):
    draft = models.ForeignKey(
        Draft,
        related_name="draft_rounds",
        on_delete=models.CASCADE,
    )
    captain = models.ForeignKey(
        User, related_name="draft_rounds_captained", on_delete=models.CASCADE
    )
    pick_number = models.IntegerField(
        default=1,
        blank=True,
        help_text="pick number starts at 1, and counts all picks",
    )
    pick_phase = models.IntegerField(
        default=1,
        blank=True,
        help_text="pick phase is only increase after all captains have picked once",
    )

    choice = models.ForeignKey(
        User,
        related_name="draftrounds_choice",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    # NEW: Tie tracking fields
    was_tie = models.BooleanField(
        default=False,
        help_text="Whether this round was determined by a tie-breaker roll",
    )
    tie_roll_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Stores tie resolution: {tied_teams, roll_rounds, winner_id}",
    )
```

**Step 2: Generate migration**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-shuffle-draft/backend
source ../.venv/bin/activate 2>/dev/null || source /home/kettle/git_repos/website/.venv/bin/activate
DISABLE_CACHE=true python manage.py makemigrations app --name draftround_tie_fields
```

Expected: Migration file created

**Step 3: Apply migration**

Run:
```bash
DISABLE_CACHE=true python manage.py migrate
```

Expected: Migration applied successfully

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add tie tracking fields to DraftRound model"
```

---

## Task 2: Add Shuffle to DraftStyles Enum and Choices

**Files:**
- Modify: `backend/app/models.py:58-61` (DraftStyles enum)
- Modify: `backend/app/models.py:457-460` (DRAFT_STYLE_CHOICES)

**Step 1: Update DraftStyles enum**

Change:
```python
class DraftStyles(StrEnum):
    snake = ("snake",)
    normal = ("normal",)
```

To:
```python
class DraftStyles(StrEnum):
    snake = "snake"
    normal = "normal"
    shuffle = "shuffle"
```

**Step 2: Update DRAFT_STYLE_CHOICES in Draft model**

Change:
```python
DRAFT_STYLE_CHOICES = [
    ("snake", "Snake"),
    ("normal", "Normal"),
]
```

To:
```python
DRAFT_STYLE_CHOICES = [
    ("snake", "Snake"),
    ("normal", "Normal"),
    ("shuffle", "Shuffle"),
]
```

**Step 3: Generate and apply migration**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-shuffle-draft/backend
DISABLE_CACHE=true python manage.py makemigrations app --name draft_style_shuffle
DISABLE_CACHE=true python manage.py migrate
```

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add shuffle to draft style choices"
```

---

## Task 3: Add total_mmr to Team Serializer

**Files:**
- Modify: `backend/app/serializers.py` (TeamSerializer)

**Step 1: Read current serializer to find TeamSerializer**

Run:
```bash
grep -n "class TeamSerializer" backend/app/serializers.py
```

**Step 2: Add total_mmr SerializerMethodField**

Add to TeamSerializer class:

```python
total_mmr = serializers.SerializerMethodField()

def get_total_mmr(self, obj):
    """Sum of captain MMR + all member MMRs (excluding captain from members to avoid double-counting)."""
    total = 0
    if obj.captain and obj.captain.mmr:
        total += obj.captain.mmr
    for member in obj.members.all():
        if member.mmr and member.pk != getattr(obj.captain, 'pk', None):
            total += member.mmr
    return total
```

Also add `'total_mmr'` to the `fields` list in Meta class.

**Step 3: Verify serializer works**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-shuffle-draft/backend
DISABLE_CACHE=true python manage.py shell -c "
from app.serializers import TeamSerializer
from app.models import Team
team = Team.objects.first()
if team:
    s = TeamSerializer(team)
    print('total_mmr:', s.data.get('total_mmr'))
else:
    print('No teams in database')
"
```

**Step 4: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat: add total_mmr computed field to TeamSerializer"
```

---

## Task 4: Implement roll_until_winner Method

**Files:**
- Modify: `backend/app/models.py` (Draft model, after `go_back` method ~line 812)

**Step 1: Add roll_until_winner method to Draft model**

Add after the `go_back` method:

```python
def roll_until_winner(self, tied_teams):
    """
    Roll dice until exactly one winner emerges.

    Args:
        tied_teams: List of Team objects that are tied

    Returns:
        tuple: (winner_team, roll_rounds) where roll_rounds is a list of
               lists containing {team_id, roll} dicts for each round
    """
    import random

    roll_rounds = []
    remaining = list(tied_teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [
            t for t in remaining
            if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll
        ]

    return remaining[0], roll_rounds
```

**Step 2: Test the method manually**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-shuffle-draft/backend
DISABLE_CACHE=true python manage.py shell -c "
from app.models import Draft, Team

# Test with mock teams
class MockTeam:
    def __init__(self, id):
        self.id = id

teams = [MockTeam(1), MockTeam(2), MockTeam(3)]
draft = Draft()
winner, rounds = draft.roll_until_winner(teams)
print(f'Winner: Team {winner.id}')
print(f'Rounds: {rounds}')
print(f'Winner is one of original teams: {winner.id in [1, 2, 3]}')
"
```

Expected: A winner is selected, rounds show the dice rolls

**Step 3: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add roll_until_winner method for tie-breaking"
```

---

## Task 5: Implement create_next_shuffle_round Method

**Files:**
- Modify: `backend/app/models.py` (Draft model, after `roll_until_winner` method)

**Step 1: Add create_next_shuffle_round method**

Add after `roll_until_winner`:

```python
def create_next_shuffle_round(self):
    """
    Calculate which team picks next based on lowest total MMR.
    Creates a new DraftRound for the next pick.

    Returns:
        dict with keys:
        - round: The created DraftRound
        - team_mmr: The MMR of the team that will pick
        - tie_resolution: Dict with tie info if a tie occurred, else None
    """
    teams = list(self.tournament.teams.all())

    if not teams:
        raise ValueError("No teams in tournament")

    # Calculate current total MMR for each team
    team_mmrs = []
    for team in teams:
        total = team.captain.mmr or 0
        for member in team.members.exclude(id=team.captain_id):
            total += member.mmr or 0
        team_mmrs.append({"team": team, "mmr": total})

    # Find lowest MMR
    min_mmr = min(t["mmr"] for t in team_mmrs)
    tied_teams_data = [t for t in team_mmrs if t["mmr"] == min_mmr]

    # Handle tie with random rolls
    tie_resolution = None
    if len(tied_teams_data) > 1:
        tied_teams = [t["team"] for t in tied_teams_data]
        winner, roll_rounds = self.roll_until_winner(tied_teams)
        tie_resolution = {
            "tied_teams": [
                {"id": t["team"].id, "name": t["team"].name, "mmr": t["mmr"]}
                for t in tied_teams_data
            ],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id,
        }
        next_team = winner
        next_mmr = next(t["mmr"] for t in tied_teams_data if t["team"].id == winner.id)
    else:
        next_team = tied_teams_data[0]["team"]
        next_mmr = tied_teams_data[0]["mmr"]

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
        tie_roll_data=tie_resolution,
    )

    return {
        "round": draft_round,
        "team_mmr": next_mmr,
        "tie_resolution": tie_resolution,
    }
```

**Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add create_next_shuffle_round method for dynamic round creation"
```

---

## Task 6: Update build_rounds for Shuffle Draft

**Files:**
- Modify: `backend/app/models.py:733-801` (Draft.build_rounds method)

**Step 1: Add shuffle handling to build_rounds**

Find the `build_rounds` method and add shuffle handling after clearing existing rounds. Replace the method:

```python
def build_rounds(self):
    logging.debug(f"Building draft rounds with style: {self.draft_style}")

    # Clear existing draft rounds
    for round in self.draft_rounds.all():
        logging.debug(
            f"Draft round {round.pk} already exists for {self.tournament.name}"
        )
        round.delete()

    teams = list(self.tournament.teams.order_by("draft_order"))
    if not teams:
        logging.error("No teams found for tournament")
        return

    # For shuffle draft, only create the first round
    if self.draft_style == "shuffle":
        # Calculate captain MMRs to determine first pick
        team_mmrs = [(t, t.captain.mmr or 0) for t in teams]
        min_mmr = min(mmr for _, mmr in team_mmrs)
        tied_teams = [t for t, mmr in team_mmrs if mmr == min_mmr]

        tie_resolution = None
        if len(tied_teams) > 1:
            winner, roll_rounds = self.roll_until_winner(tied_teams)
            tie_resolution = {
                "tied_teams": [
                    {"id": t.id, "name": t.name, "mmr": t.captain.mmr or 0}
                    for t in tied_teams
                ],
                "roll_rounds": roll_rounds,
                "winner_id": winner.id,
            }
            first_team = winner
        else:
            first_team = tied_teams[0]

        DraftRound.objects.create(
            draft=self,
            captain=first_team.captain,
            pick_number=1,
            pick_phase=1,
            was_tie=bool(tie_resolution),
            tie_roll_data=tie_resolution,
        )
        logging.debug(f"Created first shuffle draft round for {first_team.name}")
        self.save()
        return

    # Existing snake/normal logic
    num_teams = len(teams)
    picks_per_team = 4  # Each team picks 4 players after captain
    total_picks = num_teams * picks_per_team

    pick_number = 1
    phase = 1

    def create_draft_round(draft, captain, pick_num, phase_num):
        try:
            draft_round = DraftRound.objects.create(
                draft=draft,
                captain=captain,
                pick_number=pick_num,
                pick_phase=phase_num,
            )
            logging.debug(
                f"Draft round {draft_round.pk} created for {captain.username} "
                f"in phase {phase_num}, pick {pick_num}"
            )
            return True
        except IntegrityError:
            logging.error(
                f"IntegrityError: Draft round already exists for {captain.username} "
                f"in phase {phase_num}, pick {pick_num}"
            )
            return False

    # Generate draft order based on style
    for round_num in range(picks_per_team):
        if self.draft_style == "snake":
            # Snake draft: alternate direction each round
            if round_num % 2 == 0:
                pick_order = teams
            else:
                pick_order = list(reversed(teams))
        else:  # normal draft
            pick_order = teams

        for team in pick_order:
            if pick_number <= total_picks:
                create_draft_round(self, team.captain, pick_number, phase)
                pick_number += 1

        phase += 1

    logging.debug(
        f"Created {pick_number - 1} draft rounds for {self.tournament.name}"
    )
    self.save()
```

**Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: update build_rounds to handle shuffle draft style"
```

---

## Task 7: Update Pick Endpoint for Shuffle Draft

**Files:**
- Modify: `backend/app/views.py` (find the pick_player or draft pick view)

**Step 1: Find the pick endpoint**

Run:
```bash
grep -n "pick" backend/app/views.py | head -20
grep -n "def.*pick\|def.*choose" backend/app/views.py
```

**Step 2: Update the pick endpoint to handle shuffle draft**

Add after successful pick, before returning response:

```python
# For shuffle draft, create next round dynamically
if draft.draft_style == "shuffle" and draft.users_remaining.exists():
    next_pick_data = draft.create_next_shuffle_round()
    response_data["next_pick"] = {
        "captain_id": next_pick_data["round"].captain.pk,
        "team_id": next_pick_data["round"].team.pk,
        "team_name": next_pick_data["round"].team.name,
        "team_mmr": next_pick_data["team_mmr"],
    }
    if next_pick_data.get("tie_resolution"):
        response_data["tie_resolution"] = next_pick_data["tie_resolution"]
```

**Step 3: Commit**

```bash
git add backend/app/views.py
git commit -m "feat: update pick endpoint to handle shuffle draft flow"
```

---

## Task 8: Add Frontend Types for Shuffle and TieResolution

**Files:**
- Modify: `frontend/app/components/draft/types.d.ts`

**Step 1: Read current types file**

Run:
```bash
cat frontend/app/components/draft/types.d.ts
```

**Step 2: Update draft_style type and add TieResolution**

Add/modify in the types file:

```typescript
export type DraftStyleType = 'snake' | 'normal' | 'shuffle';

export interface TieResolution {
  tied_teams: Array<{
    id: number;
    name: string;
    mmr: number;
  }>;
  roll_rounds: Array<
    Array<{
      team_id: number;
      roll: number;
    }>
  >;
  winner_id: number;
}

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

Update any existing `draft_style` type from `'snake' | 'normal'` to `DraftStyleType`.

**Step 3: Commit**

```bash
git add frontend/app/components/draft/types.d.ts
git commit -m "feat: add shuffle and TieResolution types to frontend"
```

---

## Task 9: Create TieResolutionOverlay Component

**Files:**
- Create: `frontend/app/components/draft/TieResolutionOverlay.tsx`

**Step 1: Create the component file**

```typescript
import React from 'react';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { DIALOG_CSS } from '~/components/reusable/modal';
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
      <DialogContent className={`${DIALOG_CSS} max-w-md`}>
        <DialogHeader>
          <DialogTitle className="text-center text-xl">
            Tie Breaker!
          </DialogTitle>
        </DialogHeader>

        {/* Team headers */}
        <div
          className="grid gap-4 text-center"
          style={{
            gridTemplateColumns: `repeat(${tied_teams.length}, minmax(0, 1fr))`,
          }}
        >
          {tied_teams.map((team) => (
            <div
              key={team.id}
              className={team.id === winner_id ? 'font-bold' : ''}
            >
              <div className="truncate">{team.name}</div>
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
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                Round {roundIdx + 1}:
              </span>
              <div
                className="grid gap-4 text-center"
                style={{
                  gridTemplateColumns: `repeat(${tied_teams.length}, minmax(0, 1fr))`,
                }}
              >
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

**Step 2: Commit**

```bash
git add frontend/app/components/draft/TieResolutionOverlay.tsx
git commit -m "feat: add TieResolutionOverlay component"
```

---

## Task 10: Update Draft Style Modal with Shuffle Option

**Files:**
- Modify: `frontend/app/components/draft/buttons/draftStyleModal.tsx`

**Step 1: Update state type**

Change:
```typescript
const [selectedStyle, setSelectedStyle] = useState<'snake' | 'normal'>(
```

To:
```typescript
const [selectedStyle, setSelectedStyle] = useState<'snake' | 'normal' | 'shuffle'>(
```

**Step 2: Add Shuffle SelectItem after Normal**

Add in the SelectContent, after the Normal SelectItem:

```typescript
<SelectItem value="shuffle">
  <div className="flex flex-col">
    <span className="font-medium">Shuffle Draft</span>
    <span className="text-xs text-muted-foreground">
      Lowest MMR team picks first, recalculated each round
    </span>
  </div>
</SelectItem>
```

**Step 3: Add Shuffle stats display section**

Add after the Normal Draft Stats div:

```typescript
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

**Step 4: Update button text for shuffle**

Update the getButtons function to handle shuffle:

```typescript
<Button
  onClick={() => handleStyleChange(selectedStyle)}
  disabled={selectedStyle === draft.draft_style}
>
  Apply {selectedStyle === 'snake' ? 'Snake' : selectedStyle === 'normal' ? 'Normal' : 'Shuffle'} Draft
</Button>
```

**Step 5: Commit**

```bash
git add frontend/app/components/draft/buttons/draftStyleModal.tsx
git commit -m "feat: add Shuffle option to draft style modal"
```

---

## Task 11: Integrate TieResolution into Pick Flow

**Files:**
- Modify: `frontend/app/components/draft/hooks/choosePlayerHook.tsx`

**Step 1: Read the current hook**

Run:
```bash
cat frontend/app/components/draft/hooks/choosePlayerHook.tsx
```

**Step 2: Add state for tie resolution**

Add imports and state at the top of the hook:

```typescript
import { TieResolutionOverlay } from '../TieResolutionOverlay';
import type { TieResolution } from '../types';

// Inside the hook, add state:
const [tieResolution, setTieResolution] = useState<TieResolution | null>(null);
const [showTieOverlay, setShowTieOverlay] = useState(false);
```

**Step 3: Update pick handler to check for tie_resolution**

In the success handler after a pick, add:

```typescript
// Show tie overlay for shuffle draft
if (draft?.draft_style === 'shuffle' && response.data.tie_resolution) {
  setTieResolution(response.data.tie_resolution);
  setShowTieOverlay(true);
}
```

**Step 4: Return overlay state and component from hook**

Add to the hook's return value:

```typescript
return {
  // ... existing returns
  tieResolution,
  showTieOverlay,
  setShowTieOverlay,
  TieOverlay: showTieOverlay && tieResolution ? (
    <TieResolutionOverlay
      tieResolution={tieResolution}
      onDismiss={() => {
        setShowTieOverlay(false);
        setTieResolution(null);
      }}
    />
  ) : null,
};
```

**Step 5: Commit**

```bash
git add frontend/app/components/draft/hooks/choosePlayerHook.tsx
git commit -m "feat: integrate tie resolution overlay into pick flow"
```

---

## Task 12: Render TieOverlay in Draft Component

**Files:**
- Modify: `frontend/app/components/draft/draftModal.tsx` (or wherever choosePlayerHook is consumed)

**Step 1: Find where choosePlayerHook is used**

Run:
```bash
grep -rn "useChoosePlayer\|choosePlayerHook" frontend/app/components/draft/
```

**Step 2: Destructure TieOverlay from the hook**

Add `TieOverlay` to the destructured values:

```typescript
const { ..., TieOverlay } = useChoosePlayer();
```

**Step 3: Render TieOverlay in the component**

Add at the end of the component's JSX, before the closing fragment/div:

```typescript
{TieOverlay}
```

**Step 4: Commit**

```bash
git add frontend/app/components/draft/
git commit -m "feat: render tie resolution overlay in draft modal"
```

---

## Task 13: Manual Testing

**Step 1: Start the test environment**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-shuffle-draft
just test::up
```

**Step 2: Populate test data**

Run:
```bash
just db::populate::all
```

**Step 3: Test shuffle draft flow**

1. Navigate to a tournament's draft page
2. Open Draft Style modal
3. Select "Shuffle" and apply
4. Verify first pick goes to team with lowest captain MMR
5. Make a pick
6. Verify next pick recalculates based on total team MMR
7. If a tie occurs, verify the tie resolution overlay appears

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during manual testing"
```

---

## Task 14: Final Cleanup and PR Preparation

**Step 1: Run linting**

```bash
cd frontend && npm run typecheck
cd ../backend && python -m black . && python -m isort .
```

**Step 2: Ensure all tests pass**

```bash
just test::pw::headless
```

**Step 3: Squash/organize commits if needed**

Review commits:
```bash
git log --oneline -15
```

**Step 4: Push branch**

```bash
git push -u origin feature/shuffle-draft
```

---

## Summary

| Task | Description | Est. Time |
|------|-------------|-----------|
| 1 | Add migration for DraftRound tie fields | 5 min |
| 2 | Add shuffle to DraftStyles enum | 3 min |
| 3 | Add total_mmr to Team serializer | 5 min |
| 4 | Implement roll_until_winner method | 5 min |
| 5 | Implement create_next_shuffle_round method | 10 min |
| 6 | Update build_rounds for shuffle | 10 min |
| 7 | Update pick endpoint for shuffle | 10 min |
| 8 | Add frontend types | 5 min |
| 9 | Create TieResolutionOverlay component | 10 min |
| 10 | Update Draft Style Modal | 10 min |
| 11 | Integrate into pick flow hook | 10 min |
| 12 | Render overlay in draft component | 5 min |
| 13 | Manual testing | 15 min |
| 14 | Cleanup and PR | 10 min |

**Total: ~113 minutes**
