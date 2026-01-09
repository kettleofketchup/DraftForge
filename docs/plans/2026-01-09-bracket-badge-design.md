# Bracket Badge Design

**Date:** 2026-01-09
**Status:** Approved

## Purpose

Visual badges that link winners bracket games to their losers bracket destinations. When a team loses in winners bracket game "A", viewers can easily find where they go in the losers bracket by looking for the "A" badge.

## Badge Appearance

- **Shape:** Small rounded rectangle or pill shape
- **Content:** Single uppercase letter (A, B, C, D...)
- **Size:** ~20x20px, small enough to not overwhelm but readable

### Color Palette (8 colors, high contrast on dark backgrounds)

| Letter | Color | Hex |
|--------|-------|-----|
| A | Coral Red | `#FF6B6B` |
| B | Sky Blue | `#4ECDC4` |
| C | Sunny Yellow | `#FFE66D` |
| D | Lavender | `#A78BFA` |
| E | Mint Green | `#6BCB77` |
| F | Hot Pink | `#FF85A2` |
| G | Orange | `#FFA94D` |
| H | Cyan | `#22D3EE` |

Colors repeat after H (I=A's color, J=B's color, etc.)

## Badge Placement

### Winners Bracket Games

- Badge placed **outside** the game node
- Position: To the right of the node, vertically centered
- One badge per game (shows where the loser of this game goes)
- Only games with a `loser_next_game` connection display a badge

```
┌─────────────┐
│  Team 1     │
│  vs         │ ──── [A]
│  Team 2     │
└─────────────┘
```

### Losers Bracket Games

- Badges placed **outside** each team slot (not on the node itself)
- Position: To the left of each slot, indicating where that team came from
- Up to 2 badges per game (one per slot that receives a loser)

```
      ┌─────────────┐
[A]───│  (loser)    │
      │  vs         │
[B]───│  (loser)    │
      └─────────────┘
```

## Assignment Logic

Badges are assigned sequentially as the bracket is generated:

1. Traverse winners bracket games in round order (round 1, then round 2, etc.)
2. For each game with a `loser_next_game`, assign the next letter
3. Compute badge letter from game position (no database storage needed)

## Implementation

### Data Model

No database changes needed. Badge letter computed from game position:

```typescript
function getBadgeLetter(game: BracketMatch): string | null {
  // Only winners bracket games with loser path get badges
  if (game.bracketType !== 'winners' || !game.loserNextMatchId) {
    return null;
  }

  // Compute index based on round and position
  // Round 1: positions 0,1,2,3 → A,B,C,D
  // Round 2: positions 0,1 → E,F
  // etc.
  const index = getWinnersBracketIndex(game.round, game.position);
  return String.fromCharCode(65 + (index % 26)); // A-Z, then wraps
}
```

### Frontend Components

**New component:** `BracketBadge.tsx`

```typescript
interface BracketBadgeProps {
  letter: string;
  position: 'right' | 'left';  // right for winners, left for losers
  slot?: 'top' | 'bottom';     // for losers bracket slot positioning
}
```

### Color Utility

```typescript
const BADGE_COLORS = [
  '#FF6B6B', // A - Coral Red
  '#4ECDC4', // B - Sky Blue
  '#FFE66D', // C - Sunny Yellow
  '#A78BFA', // D - Lavender
  '#6BCB77', // E - Mint Green
  '#FF85A2', // F - Hot Pink
  '#FFA94D', // G - Orange
  '#22D3EE', // H - Cyan
];

function getBadgeColor(letter: string): string {
  const index = letter.charCodeAt(0) - 65; // A=0, B=1, etc.
  return BADGE_COLORS[index % BADGE_COLORS.length];
}
```

### Integration Points

- **Winners bracket nodes:** Render badge to the right of `MatchNode` component
- **Losers bracket nodes:** Render badges to the left of each team slot in `MatchNode`
- **Badge visibility:** Only show when `loserNextMatchId` exists (winners) or slot receives a loser (losers)

## Files to Modify

### Frontend

- `frontend/app/components/bracket/BracketBadge.tsx` - New component
- `frontend/app/components/bracket/utils/badgeUtils.ts` - Badge letter/color utilities
- `frontend/app/components/bracket/nodes/MatchNode.tsx` - Integrate badges
- `frontend/app/components/bracket/bracket-styles.css` - Badge styling

### No Backend Changes

This is purely a frontend visual enhancement. The `loserNextMatchId` and `loserNextMatchSlot` data already exists from the bracket save feature.

## Testing

- Visual verification that badges appear correctly
- Verify badge letters match between winners and losers brackets
- Test with different bracket sizes (4, 8, 16 teams)
- Verify colors are visible on dark background
