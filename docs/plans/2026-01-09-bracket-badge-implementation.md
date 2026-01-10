# Bracket Badge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add visual badges linking winners bracket games to their losers bracket destinations.

**Architecture:** Create a BracketBadge component with badge letter/color utilities. Modify MatchNode to render badges: outside-right for winners bracket (showing where loser goes), outside-left for losers bracket slots (showing where team came from).

**Tech Stack:** React, TypeScript, TailwindCSS, @xyflow/react

**Worktree:** `/home/kettle/git_repos/website/.worktrees/bracket-badges`

---

## Task 1: Create Badge Utility Functions

**Files:**
- Create: `frontend/app/components/bracket/utils/badgeUtils.ts`

**Step 1: Create the badge utilities file**

Create `frontend/app/components/bracket/utils/badgeUtils.ts`:

```typescript
/**
 * Badge utilities for linking winners bracket games to losers bracket destinations.
 */

// Color palette - high contrast on dark backgrounds
const BADGE_COLORS = [
  '#FF6B6B', // A - Coral Red
  '#4ECDC4', // B - Sky Blue
  '#FFE66D', // C - Sunny Yellow
  '#A78BFA', // D - Lavender
  '#6BCB77', // E - Mint Green
  '#FF85A2', // F - Hot Pink
  '#FFA94D', // G - Orange
  '#22D3EE', // H - Cyan
] as const;

/**
 * Get the badge letter for a winners bracket game based on its position.
 * Returns null if the game doesn't have a loser path.
 */
export function getBadgeLetter(
  bracketType: string,
  round: number,
  position: number,
  hasLoserPath: boolean
): string | null {
  // Only winners bracket games with loser path get badges
  if (bracketType !== 'winners' || !hasLoserPath) {
    return null;
  }

  // Calculate sequential index based on round and position
  // Round 1 has most games, each subsequent round has half
  // Round 1: positions 0,1,2,3 → indices 0,1,2,3 → A,B,C,D
  // Round 2: positions 0,1 → indices 4,5 → E,F
  // Round 3: position 0 → index 6 → G
  let index = 0;
  for (let r = 1; r < round; r++) {
    // Estimate games in earlier rounds (this is approximate, works for power-of-2 brackets)
    index += Math.pow(2, Math.max(0, 4 - r)); // Assumes max 16-team bracket
  }
  index += position;

  return String.fromCharCode(65 + (index % 26)); // A-Z, wraps after Z
}

/**
 * Get the badge color for a given letter.
 */
export function getBadgeColor(letter: string): string {
  const index = letter.charCodeAt(0) - 65; // A=0, B=1, etc.
  return BADGE_COLORS[index % BADGE_COLORS.length];
}

/**
 * Find which badge letter a losers bracket slot should display.
 * This requires knowing which winners bracket game feeds into this slot.
 */
export function getLoserSlotBadgeLetter(
  sourceGameId: string | undefined,
  allMatches: Array<{ id: string; bracketType: string; round: number; position: number; loserNextMatchId?: string }>
): string | null {
  if (!sourceGameId) return null;

  // Find the winners bracket game that feeds into this slot
  const sourceGame = allMatches.find(
    (m) => m.bracketType === 'winners' && m.loserNextMatchId === sourceGameId
  );

  if (!sourceGame) return null;

  return getBadgeLetter(
    sourceGame.bracketType,
    sourceGame.round,
    sourceGame.position,
    true
  );
}
```

**Step 2: Verify file compiles**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npx tsc --noEmit 2>&1 | grep -i badgeUtils || echo "No errors"
```

Expected: No errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/utils/badgeUtils.ts
git commit -m "feat: add badge utility functions"
```

---

## Task 2: Create BracketBadge Component

**Files:**
- Create: `frontend/app/components/bracket/BracketBadge.tsx`

**Step 1: Create the badge component**

Create `frontend/app/components/bracket/BracketBadge.tsx`:

```typescript
import { memo } from 'react';
import { cn } from '~/lib/utils';
import { getBadgeColor } from './utils/badgeUtils';

export interface BracketBadgeProps {
  /** The badge letter (A, B, C, etc.) */
  letter: string;
  /** Position relative to the node */
  position: 'right' | 'left';
  /** For losers bracket, which slot this badge is for */
  slot?: 'top' | 'bottom';
  /** Additional CSS classes */
  className?: string;
}

/**
 * Visual badge that links winners bracket games to losers bracket destinations.
 * Displays a colored letter indicating the connection.
 */
export const BracketBadge = memo(function BracketBadge({
  letter,
  position,
  slot,
  className,
}: BracketBadgeProps) {
  const color = getBadgeColor(letter);

  // Position classes based on where badge should appear
  const positionClasses = cn(
    'absolute flex items-center',
    position === 'right' && 'right-0 translate-x-full top-1/2 -translate-y-1/2 pl-1',
    position === 'left' && 'left-0 -translate-x-full pr-1',
    position === 'left' && slot === 'top' && 'top-[25%]',
    position === 'left' && slot === 'bottom' && 'top-[75%]',
    position === 'left' && !slot && 'top-1/2 -translate-y-1/2'
  );

  return (
    <div className={cn(positionClasses, className)}>
      {/* Connecting line */}
      <div
        className={cn(
          'h-px w-3',
          position === 'right' ? 'order-first' : 'order-last'
        )}
        style={{ backgroundColor: color }}
      />
      {/* Badge pill */}
      <div
        className="flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold text-black"
        style={{ backgroundColor: color }}
      >
        {letter}
      </div>
    </div>
  );
});
```

**Step 2: Verify file compiles**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npx tsc --noEmit 2>&1 | grep -i BracketBadge || echo "No errors"
```

Expected: No errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/BracketBadge.tsx
git commit -m "feat: add BracketBadge component"
```

---

## Task 3: Add Badge Context for Losers Bracket Mapping

**Files:**
- Modify: `frontend/app/components/bracket/types.ts`

**Step 1: Add badge mapping type**

Add to the end of `frontend/app/components/bracket/types.ts`:

```typescript

// Badge mapping for losers bracket slots
// Maps losers game ID + slot to the badge letter
export interface BadgeMapping {
  [gameIdAndSlot: string]: string; // e.g., "l-1-0:radiant" -> "A"
}
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/types.ts
git commit -m "feat: add BadgeMapping type"
```

---

## Task 4: Create Badge Mapping Builder

**Files:**
- Modify: `frontend/app/components/bracket/utils/badgeUtils.ts`

**Step 1: Add buildBadgeMapping function**

Append to `frontend/app/components/bracket/utils/badgeUtils.ts`:

```typescript

import type { BracketMatch, BadgeMapping } from '../types';

/**
 * Build a mapping of losers bracket slots to their source badge letters.
 * This pre-computes which badge each losers bracket slot should display.
 */
export function buildBadgeMapping(matches: BracketMatch[]): BadgeMapping {
  const mapping: BadgeMapping = {};

  // Find all winners bracket games with loser paths
  const winnersWithLoserPath = matches.filter(
    (m) => m.bracketType === 'winners' && m.loserNextMatchId && m.loserNextMatchSlot
  );

  for (const game of winnersWithLoserPath) {
    const letter = getBadgeLetter(
      game.bracketType,
      game.round,
      game.position,
      true
    );

    if (letter && game.loserNextMatchId && game.loserNextMatchSlot) {
      const key = `${game.loserNextMatchId}:${game.loserNextMatchSlot}`;
      mapping[key] = letter;
    }
  }

  return mapping;
}
```

**Step 2: Update import in file**

Update the imports at the top of `badgeUtils.ts` to include the type import:

```typescript
import type { BracketMatch, BadgeMapping } from '../types';
```

Note: Add this import at the top of the file, below the existing code.

**Step 3: Verify file compiles**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npx tsc --noEmit 2>&1 | grep -i badgeUtils || echo "No errors"
```

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/utils/badgeUtils.ts
git commit -m "feat: add buildBadgeMapping function"
```

---

## Task 5: Integrate Badges into MatchNode

**Files:**
- Modify: `frontend/app/components/bracket/nodes/MatchNode.tsx`

**Step 1: Add badge imports**

Add these imports at the top of `MatchNode.tsx` after the existing imports:

```typescript
import { BracketBadge } from '../BracketBadge';
import { getBadgeLetter } from '../utils/badgeUtils';
```

**Step 2: Update MatchNodeData to include badge info**

The MatchNodeData already extends BracketMatch, so we have access to `loserNextMatchId`. We need to add badge mapping as an optional prop.

Update the component props interface. After line 47 (`export const MatchNode = memo(...)`), the component receives `data` of type `MatchNodeData`. We need to pass badge mapping through data.

First, update `types.ts` to add badgeMapping to MatchNodeData:

In `frontend/app/components/bracket/types.ts`, update `MatchNodeData`:

```typescript
// React Flow node data - index signature required for @xyflow/react Node<T> compatibility
export interface MatchNodeData extends BracketMatch {
  // Badge mapping for this node (passed from parent)
  badgeMapping?: BadgeMapping;
  // Additional display properties can go here
  [key: string]: unknown;
}
```

**Step 3: Add badges to MatchNode render**

In `MatchNode.tsx`, add badge rendering. Replace the component's return statement (starting at line 52) with:

```typescript
  // Calculate badge for winners bracket
  const winnersBadgeLetter =
    data.bracketType === 'winners' && data.loserNextMatchId
      ? getBadgeLetter(data.bracketType, data.round, data.position, true)
      : null;

  // Get badges for losers bracket slots
  const radiantBadgeLetter = data.badgeMapping?.[`${data.id}:radiant`];
  const direBadgeLetter = data.badgeMapping?.[`${data.id}:dire`];

  return (
    <BaseNode
      className={cn(
        'w-52 cursor-pointer transition-all relative',
        bracketStyle.bg,
        bracketStyle.border,
        selected && 'ring-2 ring-primary'
      )}
    >
      {/* Left handle - receives winner from previous match */}
      <BaseHandle type="target" position={Position.Left} />

      {/* Losers bracket badges - left side of slots */}
      {data.bracketType === 'losers' && radiantBadgeLetter && (
        <BracketBadge letter={radiantBadgeLetter} position="left" slot="top" />
      )}
      {data.bracketType === 'losers' && direBadgeLetter && (
        <BracketBadge letter={direBadgeLetter} position="left" slot="bottom" />
      )}

      {/* Header with round label and status */}
      <BaseNodeHeader className={cn('border-b pb-2', bracketStyle.headerBg)}>
        <BaseNodeHeaderTitle className="text-xs text-muted-foreground">
          {roundLabel}
        </BaseNodeHeaderTitle>
        <Badge variant="outline" className={cn('text-xs', status.className)}>
          {status.label}
        </Badge>
      </BaseNodeHeader>

      {/* Team slots */}
      <BaseNodeContent className="gap-1 p-2">
        <TeamSlot
          team={data.radiantTeam}
          score={data.radiantScore}
          isWinner={data.winner === 'radiant'}
          isCompleted={data.status === 'completed'}
        />
        <div className="border-t my-1" />
        <TeamSlot
          team={data.direTeam}
          score={data.direScore}
          isWinner={data.winner === 'dire'}
          isCompleted={data.status === 'completed'}
        />
      </BaseNodeContent>

      {/* Right handle - winner advances to next match */}
      <BaseHandle type="source" position={Position.Right} />

      {/* Winners bracket badge - right side */}
      {winnersBadgeLetter && (
        <BracketBadge letter={winnersBadgeLetter} position="right" />
      )}
    </BaseNode>
  );
```

**Step 4: Verify file compiles**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npx tsc --noEmit 2>&1 | head -20
```

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/nodes/MatchNode.tsx frontend/app/components/bracket/types.ts
git commit -m "feat: integrate badges into MatchNode"
```

---

## Task 6: Pass Badge Mapping to Nodes in BracketView

**Files:**
- Modify: `frontend/app/components/bracket/BracketView.tsx`

**Step 1: Import badge utilities**

Add import at the top of `BracketView.tsx`:

```typescript
import { buildBadgeMapping } from './utils/badgeUtils';
```

**Step 2: Build badge mapping and pass to nodes**

Find where nodes are created from matches and add badge mapping to each node's data. This requires finding the code that transforms `BracketMatch[]` into React Flow nodes.

Search for where `data` is assigned to nodes and add `badgeMapping` to the data object:

```typescript
// Where nodes are built, compute the badge mapping once
const badgeMapping = useMemo(() => buildBadgeMapping(matches), [matches]);

// Then when creating node data, include the mapping:
// data: { ...match, badgeMapping }
```

The exact location depends on how BracketView creates nodes. Look for patterns like:
- `matches.map(match => ({ ...match, ...`
- `setNodes(` or similar React Flow node creation

**Step 3: Verify file compiles**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npx tsc --noEmit 2>&1 | head -20
```

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/BracketView.tsx
git commit -m "feat: pass badge mapping to bracket nodes"
```

---

## Task 7: Add Export to Index File

**Files:**
- Modify: `frontend/app/components/bracket/index.ts`

**Step 1: Add BracketBadge export**

Add to `frontend/app/components/bracket/index.ts`:

```typescript
export { BracketBadge } from './BracketBadge';
export * from './utils/badgeUtils';
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git add frontend/app/components/bracket/index.ts
git commit -m "feat: export badge components"
```

---

## Task 8: Build and Visual Test

**Step 1: Run full build**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges/frontend
npm run build
```

Expected: Build succeeds

**Step 2: Visual verification (if dev server available)**

Start dev server and navigate to a tournament bracket to verify badges appear correctly.

**Step 3: Final commit if any cleanup needed**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-badges
git status
# If changes exist:
git add -A
git commit -m "chore: cleanup badge implementation"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Badge utility functions | `utils/badgeUtils.ts` |
| 2 | BracketBadge component | `BracketBadge.tsx` |
| 3 | BadgeMapping type | `types.ts` |
| 4 | buildBadgeMapping function | `utils/badgeUtils.ts` |
| 5 | Integrate badges into MatchNode | `nodes/MatchNode.tsx`, `types.ts` |
| 6 | Pass badge mapping in BracketView | `BracketView.tsx` |
| 7 | Export from index | `index.ts` |
| 8 | Build and visual test | - |
