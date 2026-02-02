# Bracket Unset Winner - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow unsetting the winner of a bracket game, with proper state cleanup.

**Architecture:** Backend `advance_winner` endpoint accepts `winner: null` to clear winner, reset status, and clear placement. Frontend adds `unsetMatchWinner` action and UI button.

**Tech Stack:** Django REST Framework, React, Zustand, Zod, Playwright

**Worktree:** `/home/kettle/git_repos/website/.worktrees/bracket-unset-winner`

---

## Task 1: Backend - Modify advance_winner endpoint

**Files:**
- Modify: `backend/app/views/bracket.py`

**Step 1: Read current advance_winner function**

Read the file to understand current implementation.

**Step 2: Add unset winner logic**

At the start of `advance_winner`, after permission check, add handling for `winner is None`:

```python
winner = request.data.get("winner")

# Handle unset case
if winner is None:
    if game.winning_team:
        # Find losing team to clear their placement
        losing_team = game.dire_team if game.winning_team == game.radiant_team else game.radiant_team
        if losing_team and losing_team.placement:
            losing_team.placement = None
            losing_team.save()

    game.winning_team = None
    game.status = "scheduled"
    game.save()
    return Response(GameSerializer(game).data)

# Existing validation and set-winner logic continues...
```

**Step 3: Commit**

```bash
git add backend/app/views/bracket.py
git commit -m "feat: allow unsetting bracket game winner via advance_winner endpoint"
```

---

## Task 2: Backend Test - Test unset winner

**Files:**
- Create or modify: `backend/app/tests/test_bracket.py`

**Step 1: Write test for unset winner**

```python
def test_advance_winner_unset(self):
    """Test that advance_winner with winner=null clears the winner."""
    # Setup: Create game with winner set
    game = Game.objects.create(
        tournament=self.tournament,
        radiant_team=self.team1,
        dire_team=self.team2,
        winning_team=self.team1,
        status="completed",
    )
    # Set placement on losing team
    self.team2.placement = 3
    self.team2.save()

    # Act: Call advance_winner with winner=null
    self.client.force_authenticate(user=self.staff_user)
    response = self.client.post(
        f"/api/bracket/games/{game.pk}/advance-winner/",
        {"winner": None},
        format="json",
    )

    # Assert
    self.assertEqual(response.status_code, 200)
    game.refresh_from_db()
    self.team2.refresh_from_db()
    self.assertIsNone(game.winning_team)
    self.assertEqual(game.status, "scheduled")
    self.assertIsNone(self.team2.placement)
```

**Step 2: Run test**

Run: `cd /home/kettle/git_repos/website/.worktrees/bracket-unset-winner && just test::run 'python manage.py test app.tests.test_bracket -v 2'`

**Step 3: Commit**

```bash
git add backend/app/tests/test_bracket.py
git commit -m "test: add test for unsetting bracket game winner"
```

---

## Task 3: Frontend - Create bracketAPI.tsx

**Files:**
- Create: `frontend/app/components/api/bracketAPI.tsx`

**Step 1: Create API file with Zod schemas**

```typescript
import { z } from 'zod';
import { api } from './axios';
import { BracketResponseSchema, type BracketResponse } from '~/components/bracket/schemas';
import type { BracketMatch } from '~/components/bracket/types';

// Save bracket
export async function saveBracket(
  tournamentId: number,
  matches: BracketMatch[]
): Promise<BracketResponse> {
  const response = await api.post(`/bracket/tournaments/${tournamentId}/save/`, {
    matches,
  });
  return BracketResponseSchema.parse(response.data);
}

// Load bracket
export async function loadBracket(tournamentId: number): Promise<BracketResponse> {
  const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
  return BracketResponseSchema.parse(response.data);
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/api/bracketAPI.tsx
git commit -m "feat: add bracketAPI.tsx with Zod-validated API functions"
```

---

## Task 4: Frontend - Update bracketStore to use bracketAPI

**Files:**
- Modify: `frontend/app/store/bracketStore.ts`

**Step 1: Update imports and saveBracket**

Replace inline `api.post` call in `saveBracket` with import from bracketAPI:

```typescript
import { saveBracket as saveBracketAPI, loadBracket as loadBracketAPI } from '~/components/api/bracketAPI';

// In saveBracket action:
saveBracket: async (tournamentId) => {
  set({ isLoading: true });
  try {
    const data = await saveBracketAPI(tournamentId, get().matches);
    const savedMatches = data.matches.map(m => mapApiMatchToMatch(m, data.matches));
    set({
      matches: savedMatches,
      isDirty: false,
      isVirtual: false,
      isLoading: false,
    });
  } catch (error) {
    set({ isLoading: false });
    throw error;
  }
},
```

**Step 2: Update loadBracket**

Replace inline `api.get` call in `loadBracket` with import from bracketAPI.

**Step 3: Commit**

```bash
git add frontend/app/store/bracketStore.ts
git commit -m "refactor: use bracketAPI for API calls in bracketStore"
```

---

## Task 5: Frontend - Add unsetMatchWinner action

**Files:**
- Modify: `frontend/app/store/bracketStore.ts`

**Step 1: Add interface and action**

Add to interface:
```typescript
unsetMatchWinner: (matchId: string) => void;
```

Add action:
```typescript
unsetMatchWinner: (matchId) => {
  const match = get().matches.find((m) => m.id === matchId);
  if (!match?.winner) return;

  const winningTeam = match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
  const losingTeam = match.winner === 'radiant' ? match.direTeam : match.radiantTeam;

  set((state) => ({
    matches: state.matches.map((m) => {
      if (m.id === matchId) {
        return { ...m, winner: undefined, status: 'pending' as const };
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

**Step 2: Commit**

```bash
git add frontend/app/store/bracketStore.ts
git commit -m "feat: add unsetMatchWinner action to bracketStore"
```

---

## Task 6: Frontend - Add Unset Winner button to UI

**Files:**
- Modify: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**Step 1: Import unsetMatchWinner**

Add to destructured imports from useBracketStore:
```typescript
const { setMatchWinner, advanceWinner, loadBracket, unsetMatchWinner } = useBracketStore();
```

**Step 2: Add handler**

```typescript
const handleUnsetWinner = () => {
  unsetMatchWinner(match.id);
};
```

**Step 3: Add button after existing staff controls**

After the "Set Winner" section, add:
```typescript
{/* Unset Winner - only show if match has winner */}
{isStaff && match.status === 'completed' && match.winner && (
  <div className="border-t pt-4">
    <Button
      variant="outline"
      onClick={handleUnsetWinner}
      data-testid="unsetWinnerButton"
    >
      <RotateCcw className="w-4 h-4 mr-1" />
      Unset Winner
    </Button>
  </div>
)}
```

**Step 4: Commit**

```bash
git add frontend/app/components/bracket/modals/MatchStatsModal.tsx
git commit -m "feat: add Unset Winner button to MatchStatsModal"
```

---

## Task 7: Playwright Test - Test unset winner flow

**Files:**
- Create: `frontend/tests/playwright/e2e/bracket/unset-winner.spec.ts`

**Step 1: Write Playwright test**

```typescript
import { test, expect } from '@playwright/test';
import { loginAsStaff, createTestTournament } from '../helpers';

test.describe('Bracket Unset Winner', () => {
  test('staff can unset a bracket game winner', async ({ page }) => {
    await loginAsStaff(page);
    // Navigate to tournament with bracket
    // Set a winner
    // Click Unset Winner
    // Verify winner is cleared
    // Save bracket
    // Reload and verify persistence
  });
});
```

**Step 2: Run test**

Run: `just test::pw::spec unset-winner`

**Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/bracket/unset-winner.spec.ts
git commit -m "test: add Playwright test for unset bracket winner"
```

---

## Task 8: Add backend test to CI

**Files:**
- Modify: `.github/workflows/playwright.yml` or create dedicated backend test workflow

**Step 1: Add bracket test to CI**

Ensure backend bracket tests run in CI pipeline.

**Step 2: Commit**

```bash
git add .github/workflows/
git commit -m "ci: add bracket backend tests to CI pipeline"
```
