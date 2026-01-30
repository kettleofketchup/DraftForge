# UserStrip Component Design

## Overview

Extract the inline `PlayerRow` component from `draftRoundView.tsx` into a reusable `UserStrip` component with a flexible slot-based API.

## Use Cases

- Team draft pick lists
- Compacted team player views
- Any horizontal user display needing contextual data and actions

## Component API

```typescript
interface UserStripProps {
  user: UserType;  // Plain object type, not class instance

  // Named slots
  contextSlot?: React.ReactNode;
  actionSlot?: React.ReactNode;

  // Optional context for mini-profile popover
  leagueId?: number;
  organizationId?: number;

  // Optional styling
  className?: string;
}
```

## Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ [Avatar]  Username                    │ Context Data │ [Action]   │
│           B: 6,700  L: —              │ → 9,100      │ [Pick]     │
│           [1][2][3][4][5] (positions) │ 3rd          │            │
└────────────────────────────────────────────────────────────────────┘
   Column 1 (fixed)                       Column 2       Column 3
                                          (flexible)     (optional)
```

- **Column 1**: Avatar, name, base MMR, league MMR, position icons (always shown)
- **Column 2**: Contextual slot - parent provides content (optional)
- **Column 3**: Action button slot - parent provides button (optional)

## Efficiency

- Custom `memo` comparator to avoid re-renders on parent state changes
- Shallow positions array check (deep compare expensive for lists)
- Slots use referential equality (parent controls slot memoization)
- No internal state - pure display component

## File Location

```
frontend/app/components/user/UserStrip.tsx
```

## Usage Examples

```tsx
// Draft pick list - with context and action
<UserStrip
  user={player}
  contextSlot={<PickOrderInfo mmr={9100} position="3rd" />}
  actionSlot={<Button size="sm">Pick</Button>}
/>

// Team roster view - minimal
<UserStrip user={player} />

// Team roster with remove action
<UserStrip
  user={player}
  actionSlot={<RemovePlayerButton userId={player.pk} />}
/>
```

## Implementation Tasks

1. Create `UserStrip.tsx` component
2. Export from `user/index.tsx`
3. Update `draftRoundView.tsx` to use `UserStrip` instead of inline `PlayerRow`
