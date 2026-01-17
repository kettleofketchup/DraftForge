# Captain & Player Popovers Design

**Date:** 2026-01-16
**Status:** Draft

## Overview

Add interactive popovers for captains and players throughout the application:

1. **Captain Popover** - Shows team roster + stats when hovering over captain during draft order
2. **Player Popover/Modal** - Shows player preview on hover, full profile on click (everywhere players appear)
3. **Jokes System** - Humorous "Under Construction" extended profile with purchasable tangoes

## Features

### Captain Popover (Draft Order)

**Location:** Draft order UI during tournament drafts only

**Behavior:**
- Hover over captain name/avatar → popover appears
- Mouse leaves → popover closes
- No click-to-modal (keeps draft flow smooth)

**Content:**
```
┌─────────────────────────────────┐
│ [Team Name]          Avg: 4250  │
├─────────────────────────────────┤
│ Member       MMR    Positions   │
│ ─────────────────────────────── │
│ 🎖 Captain   4500   1, 2        │
│ Player2      4200   3, 4        │
│ Player3      4050   4, 5        │
│ (empty slots shown as "—")      │
└─────────────────────────────────┘
```

- Reuses `TeamTable` component
- Shows "No players drafted yet" if team only has captain
- Header displays team name + average MMR

### Player Popover (Hover Preview)

**Location:** Everywhere players/users appear (draft pools, team tables, captain tables, etc.)

**Behavior:**
- Hover over player → popover appears with simplified info
- Click player → popover converts to modal with full profile
- Escape or click outside → closes

**Content:**
```
┌───────────────────────────────┐
│ [Avatar]  bucketoffish        │
│           MMR: 4200           │
│                               │
│ Positions: 1, 2, 3            │
│                               │
│ Click for full profile        │
└───────────────────────────────┘
```

- Compact card (~200px wide)
- Avatar 48x48px
- Subtle hint text at bottom
- Fade + slight scale animation

### Player Modal (Full Profile)

**Trigger:** Click on player popover or player element

**Layout:**
```
┌─────────────────────────────────────────────────┐
│                                             [X] │
│  ┌──────────────────────────────────────────┐   │
│  │         FULL USER CARD SECTION           │   │
│  │                                          │   │
│  │  [Avatar]   bucketoffish      [Staff]    │   │
│  │             MMR: 4200                    │   │
│  │             Steam: 123456789             │   │
│  │                                          │   │
│  │  Positions: ① ② ③ ④ ⑤                   │   │
│  │                                          │   │
│  │  [Dotabuff]  [Edit] (staff only)         │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │       EXTENDED PROFILE SECTION           │   │
│  │                                          │   │
│  │     🚧 UNDER CONSTRUCTION 🚧             │   │
│  │                                          │   │
│  │   (Jokes content - see below)            │   │
│  │                                          │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Under Construction Section (Jokes)

**Content:**
```
┌──────────────────────────────────────────────────┐
│       🚧 EXTENDED PROFILE UNDER CONSTRUCTION 🚧   │
│                                                  │
│  To unlock bucketoffish's extended profile:      │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Option A: Throw 10 of bucketoffish's games│  │
│  │                                            │  │
│  │  Progress: ██░░░░░░░░ 2/10 games thrown    │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│                      — OR —                      │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Option B: Purchase 46,326 tangoes         │  │
│  │                                            │  │
│  │  🌿 Your tangoes: 12 / 46,326              │  │
│  │                                            │  │
│  │  [🌿 Buy Tango] (logged in users only)     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

- "bucketoffish" is replaced with the viewed player's name
- Buy Tango button only visible when logged in
- Each click increments user's tango count by 1
- Progress updates in real-time

## Database Schema

### New Model: `Joke`

```python
class Joke(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='joke')
    tangoes_purchased = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Joke"
        verbose_name_plural = "Jokes"

    def __str__(self):
        return f"{self.user.username} - {self.tangoes_purchased} tangoes"
```

### API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/jokes/tangoes/` | Get current user's tango count | Required |
| POST | `/api/jokes/tangoes/buy/` | Increment tango count by 1 | Required |

**GET Response:**
```json
{
  "tangoes_purchased": 12
}
```

**POST Response:**
```json
{
  "tangoes_purchased": 13,
  "message": "You bought a tango! 🌿"
}
```

## Component Architecture

### New Components

```
frontend/app/components/
├── captain/
│   └── CaptainPopover.tsx       # Hover popover showing team during draft
├── player/
│   ├── PlayerPopover.tsx        # Hover popover (simplified UserCard)
│   ├── PlayerModal.tsx          # Full profile modal with UserCard + jokes
│   └── PlayerUnderConstruction.tsx  # The jokes section with tangoes/games
├── hooks/
│   └── useTangoes.ts            # Fetch/buy tangoes API integration
```

### Reused Components

- `TeamTable` - For captain's team roster display
- `UserCard` - Base for player modal content
- `Popover` - shadcn/ui primitive
- `Dialog` - shadcn/ui primitive for modal

### Component Details

**CaptainPopover.tsx**
```typescript
interface CaptainPopoverProps {
  captain: UserType;
  team: TeamType;
  children: React.ReactNode;  // The trigger element
}
```

**PlayerPopover.tsx**
```typescript
interface PlayerPopoverProps {
  player: UserType;
  children: React.ReactNode;  // The trigger element
}
// Manages hover→popover and click→modal state transitions
```

**PlayerModal.tsx**
```typescript
interface PlayerModalProps {
  player: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

**PlayerUnderConstruction.tsx**
```typescript
interface PlayerUnderConstructionProps {
  playerName: string;
}
```

**useTangoes.ts**
```typescript
interface UseTangoesReturn {
  tangoes: number;
  isLoading: boolean;
  buyTango: () => Promise<void>;
  isBuying: boolean;
}
```

## Integration Points

### Files to Modify

| File | Change |
|------|--------|
| Draft order component | Wrap captains with `CaptainPopover` |
| `TeamTable` | Wrap member names with `PlayerPopover` |
| `CaptainTable` | Wrap names with `PlayerPopover` |
| Draft pool components | Wrap player cards with `PlayerPopover` |

### State Management

**PlayerPopover State:**
- `isHovering` - Controls popover visibility
- `isModalOpen` - Controls modal visibility
- Click sets `isModalOpen=true` and closes popover

**Tangoes State:**
- Managed via `useTangoes` hook
- Uses React Query for caching and optimistic updates

## Implementation Order

1. **Backend: Joke model & API**
   - Create model
   - Add migration
   - Create serializer
   - Add viewset with tangoes/buy actions
   - Register URL routes

2. **Frontend: Core components**
   - `useTangoes` hook
   - `PlayerUnderConstruction` component
   - `PlayerModal` component
   - `PlayerPopover` component
   - `CaptainPopover` component

3. **Frontend: Integration**
   - Add `CaptainPopover` to draft order view
   - Add `PlayerPopover` to TeamTable
   - Add `PlayerPopover` to CaptainTable
   - Add `PlayerPopover` to other player displays

4. **Testing**
   - Backend API tests
   - Component tests
   - E2E tests for popover interactions

## Notes

- The "games thrown" counter is purely decorative (always shows 2/10)
- Tangoes are persistent per user but serve no actual purpose (it's a joke)
- The 46,326 tango requirement is intentionally absurd
