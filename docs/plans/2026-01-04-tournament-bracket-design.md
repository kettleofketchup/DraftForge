# Tournament Bracket Component Design

**Date**: 2026-01-04
**Status**: Approved
**Scope**: Frontend-focused - React Flow bracket visualization with backend support

## Overview

Create a tournament bracket component using React Flow for the `/tournament/games` tab. Supports double elimination brackets (Challonge-style) with auto-generation, manual editing, and live polling updates. Includes stubs for Swiss bracket support.

## Goals

1. Visualize double elimination brackets with winners/losers/grand finals
2. Auto-generate bracket structure from tournament teams
3. Support multiple seeding methods (MMR, random, manual)
4. Allow staff to manually edit bracket positions and set winners
5. Provide live updates via polling for spectators
6. Click matches to view stats (integrates with Steam match PR)
7. Stub Swiss bracket support for future implementation

## Non-Goals

- WebSocket real-time updates (future enhancement)
- Full Swiss bracket implementation (stubs only)
- Steam match linking UI (handled by separate PR)

---

## Architecture

### Component Structure

```
frontend/app/components/bracket/
├── BracketView.tsx           # Main React Flow canvas wrapper
├── nodes/
│   ├── MatchNode.tsx         # Custom node for match display
│   └── EmptySlotNode.tsx     # Empty slot for team assignment
├── edges/
│   └── BracketEdge.tsx       # Custom edge with winner flow styling
├── modals/
│   └── MatchStatsModal.tsx   # View match stats (integrates with Steam PR)
├── controls/
│   ├── BracketToolbar.tsx    # Generate, save, seeding options (staff only)
│   ├── SeedingDropdown.tsx   # Random/MMR seeding options
│   └── TeamDragOverlay.tsx   # Drag-and-drop team assignment
├── hooks/
│   ├── useElkLayout.ts       # ELK.js automatic layout
│   ├── useBracketPolling.ts  # Live update polling
│   └── useBracketPersistence.ts  # Save/load bracket to API
├── utils/
│   ├── doubleElimination.ts  # Bracket structure generator
│   ├── swissBracket.ts       # Swiss bracket stubs
│   ├── bracketFactory.ts     # Factory for bracket types
│   └── seeding.ts            # Seeding algorithms
├── views/
│   └── SwissBracketView.tsx  # Swiss-specific view (stub)
├── types.ts                  # TypeScript types
└── schemas.ts                # Zod schemas
```

### Data Flow

1. Tournament loaded → Check for existing Games → Display bracket OR show "Generate" button
2. Staff generates bracket → Virtual state in Zustand → Staff saves → POST to API creates Games
3. Polling fetches updated Games → React Flow re-renders → Spectators see changes

---

## Data Types

### Frontend Types (`types.ts`)

```typescript
export type BracketType = 'winners' | 'losers' | 'grand_finals';
export type MatchStatus = 'pending' | 'live' | 'completed';
export type SeedingMethod = 'random' | 'mmr_total' | 'captain_mmr' | 'manual';

export interface BracketMatch {
  id: string;                    // Temporary ID until persisted
  gameId?: number;               // Backend Game.pk after save
  round: number;                 // Round number within bracket type
  position: number;              // Position within round (0-indexed)
  bracketType: BracketType;
  radiantTeam?: TeamType;
  direTeam?: TeamType;
  radiantScore?: number;
  direScore?: number;
  winner?: 'radiant' | 'dire';
  status: MatchStatus;
  steamMatchId?: number;         // Linked Steam match (from other PR)
  nextMatchId?: string;          // Winner advances to this match
  nextMatchSlot?: 'radiant' | 'dire';
}

export interface BracketState {
  tournamentId: number;
  bracketType: 'double_elimination' | 'swiss';
  matches: BracketMatch[];
  isDirty: boolean;
  isVirtual: boolean;
}
```

### Zod Schemas (`schemas.ts`)

```typescript
export const BracketMatchSchema = z.object({
  id: z.string(),
  gameId: z.number().optional(),
  round: z.number(),
  position: z.number(),
  bracketType: z.enum(['winners', 'losers', 'grand_finals']),
  radiantTeamId: z.number().optional(),
  direTeamId: z.number().optional(),
  winnerId: z.number().optional(),
  status: z.enum(['pending', 'live', 'completed']),
  steamMatchId: z.number().optional(),
});

export const BracketResponseSchema = z.object({
  tournamentId: z.number(),
  matches: z.array(BracketMatchSchema),
});
```

---

## Double Elimination Bracket Generator

### Structure Rules

For N teams:
- **Winners Bracket**: `ceil(log2(N))` rounds
- **Losers Bracket**: `2 * (ceil(log2(N)) - 1)` rounds
- **Grand Finals**: 1-2 matches (bracket reset if losers winner wins first)

### Generation Algorithm (`utils/doubleElimination.ts`)

```typescript
export function generateDoubleElimination(teams: TeamType[]): BracketMatch[] {
  const n = teams.length;
  const rounds = Math.ceil(Math.log2(n));
  const matches: BracketMatch[] = [];

  // 1. Generate winners bracket structure
  // 2. Generate losers bracket structure
  // 3. Generate grand finals
  // 4. Connect matches via nextMatchId/nextMatchSlot

  return matches;
}
```

### Seeding Functions (`utils/seeding.ts`)

```typescript
export function seedByMMR(teams: TeamType[]): TeamType[];
export function seedByCaptainMMR(teams: TeamType[]): TeamType[];
export function seedRandom(teams: TeamType[]): TeamType[];
export function applyBracketSeeding(sortedTeams: TeamType[], matches: BracketMatch[]): BracketMatch[];
```

---

## React Flow + ELK Layout

### Dependencies

```bash
npm install elkjs
```

### ELK Layout Hook (`hooks/useElkLayout.ts`)

```typescript
import ELK from 'elkjs/lib/elk.bundled.js';

const elkOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.spacing.nodeNode': '80',
  'elk.layered.spacing.nodeNodeBetweenLayers': '150',
  'elk.portConstraints': 'FIXED_ORDER',
};

export function useElkLayout() {
  const getLayoutedElements = useCallback(
    async (nodes: Node[], edges: Edge[], options = {}) => {
      const graph = {
        id: 'root',
        layoutOptions: { ...elkOptions, ...options },
        children: nodes.map((node) => ({
          id: node.id,
          width: 192,
          height: 100,
          ports: [
            { id: `${node.id}-target`, properties: { side: 'WEST' } },
            { id: `${node.id}-source`, properties: { side: 'EAST' } },
          ],
        })),
        edges: edges.map((edge) => ({
          id: edge.id,
          sources: [`${edge.source}-source`],
          targets: [`${edge.target}-target`],
        })),
      };

      const layoutedGraph = await elk.layout(graph);

      // Map ELK positions back to React Flow nodes
      const layoutedNodes = nodes.map((node) => {
        const elkNode = layoutedGraph.children?.find((n) => n.id === node.id);
        return {
          ...node,
          position: { x: elkNode?.x ?? 0, y: elkNode?.y ?? 0 },
        };
      });

      return { nodes: layoutedNodes, edges };
    },
    []
  );

  return { getLayoutedElements };
}
```

### Bracket Layout

- Winners bracket: y = 0 to midpoint
- Losers bracket: y = midpoint + gap to bottom
- Grand finals: rightmost x position
- Layout each section separately, then combine with offsets

---

## Backend API Changes

### Game Model Updates (`backend/app/models.py`)

```python
class Game(models.Model):
    tournament = models.ForeignKey(...)
    round = models.IntegerField(default=1)

    # NEW: Bracket positioning fields
    bracket_type = models.CharField(
        max_length=20,
        choices=[
            ('winners', 'Winners Bracket'),
            ('losers', 'Losers Bracket'),
            ('grand_finals', 'Grand Finals'),
        ],
        default='winners',
    )
    position = models.IntegerField(default=0)

    # NEW: Match flow
    next_game = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='source_games',
    )
    next_game_slot = models.CharField(
        max_length=10,
        choices=[('radiant', 'Radiant'), ('dire', 'Dire')],
        null=True,
        blank=True,
    )

    # NEW: Match status
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('live', 'Live'),
            ('completed', 'Completed'),
        ],
        default='pending',
    )

    # Existing fields unchanged
    radiant_team = models.ForeignKey(...)
    dire_team = models.ForeignKey(...)
    winning_team = models.ForeignKey(...)
    gameid = models.IntegerField(...)  # Steam match link
```

### API Endpoints

| Endpoint | Method | Permission | Description |
|----------|--------|------------|-------------|
| `/api/tournaments/{id}/bracket/` | GET | AllowAny | Get bracket structure |
| `/api/tournaments/{id}/bracket/generate/` | POST | IsStaff | Generate bracket from teams |
| `/api/tournaments/{id}/bracket/save/` | POST | IsStaff | Persist virtual bracket to DB |
| `/api/tournaments/{id}/bracket/seed/` | POST | IsStaff | Re-seed teams in bracket |
| `/api/games/{id}/advance-winner/` | POST | IsStaff | Mark winner & advance |

### Serializer

```python
class BracketGameSerializer(serializers.ModelSerializer):
    radiant_team = TeamSerializer(read_only=True)
    dire_team = TeamSerializer(read_only=True)
    winning_team = TeamSerializer(read_only=True)

    class Meta:
        model = Game
        fields = [
            'pk', 'round', 'position', 'bracket_type',
            'radiant_team', 'dire_team', 'winning_team',
            'status', 'next_game', 'next_game_slot', 'gameid'
        ]
```

---

## State Management (Zustand)

### Bracket Store (`store/bracketStore.ts`)

```typescript
interface BracketStore {
  // State
  matches: BracketMatch[];
  nodes: Node[];
  edges: Edge[];
  isDirty: boolean;
  isVirtual: boolean;
  isLoading: boolean;
  pollInterval: number | null;

  // Actions
  setMatches: (matches: BracketMatch[]) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;

  // Bracket operations
  generateBracket: (teams: TeamType[], method: SeedingMethod) => void;
  reseedBracket: (method: SeedingMethod) => void;
  assignTeamToSlot: (matchId: string, slot: 'radiant' | 'dire', team: TeamType) => void;
  removeTeamFromSlot: (matchId: string, slot: 'radiant' | 'dire') => void;
  setMatchWinner: (matchId: string, winner: 'radiant' | 'dire') => void;
  advanceWinner: (matchId: string) => void;

  // Persistence
  saveBracket: (tournamentId: number) => Promise<void>;
  loadBracket: (tournamentId: number) => Promise<void>;
  resetBracket: () => void;

  // Polling (5 second interval)
  startPolling: (tournamentId: number, intervalMs?: number) => void;
  stopPolling: () => void;
}
```

---

## Component Details

### MatchNode

Displays detailed match information:
- Team names with avatars
- Scores (when completed)
- Status badge (Upcoming/LIVE/Final)
- Round label (Winners R1, Losers R2, Grand Finals)
- Winner highlight (green background, checkmark)
- TBD placeholder for unassigned slots

Uses existing `BaseNode`, `BaseHandle` components from `~/components/ui/`.

### BracketToolbar (Staff Only)

Controls gated by `isStaff()` from userStore:
- Generate/Reseed dropdown (MMR Total, Captain MMR, Random)
- Save Bracket button (disabled when not dirty)
- Reset button with confirmation dialog
- Team count indicator

### MatchStatsModal

Opens on match click:
- Overview tab: Team cards, winner selection (staff)
- Player Stats tab: Stats from Steam match (integrates with Steam PR)
- Match History tab: Timeline (future)
- Steam match linker stub (staff only)

---

## Swiss Bracket Stubs

### Types

```typescript
export interface SwissConfig {
  teams: TeamType[];
  rounds: number;
  winsToAdvance: number;
  lossesToEliminate: number;
}

export interface SwissStanding {
  team: TeamType;
  wins: number;
  losses: number;
  buchholz: number;
  status: 'active' | 'advanced' | 'eliminated';
}

export interface SwissRound {
  roundNumber: number;
  matches: BracketMatch[];
  standings: SwissStanding[];
}
```

### Stub Functions (`utils/swissBracket.ts`)

```typescript
export function generateSwissBracket(config: SwissConfig): SwissRound[];
export function generateSwissPairings(standings: SwissStanding[], previousMatches: BracketMatch[]): BracketMatch[];
export function calculateSwissStandings(currentStandings: SwissStanding[], completedMatches: BracketMatch[], config: SwissConfig): SwissStanding[];
export function isSwissComplete(standings: SwissStanding[], config: SwissConfig): boolean;
export function getSwissAdvancers(standings: SwissStanding[]): TeamType[];
```

### SwissBracketView (Stub)

- Standings table with W-L records
- Round selector
- Match cards per round
- Status badges (Active/Advanced/Eliminated)

---

## Polling Strategy

- Uses existing Redis cache infrastructure
- 5 second polling interval for live updates
- Polling pauses when staff has unsaved changes (`isDirty`)
- Polling resumes after save or on page load
- `useEffect` cleanup stops polling on unmount

---

## Permissions

- **All users**: View bracket, click matches to see stats
- **Staff only** (`isStaff()`):
  - Generate/reseed bracket
  - Save bracket to DB
  - Set match winners
  - Drag teams to slots
  - Reset bracket

---

## Integration Points

### Steam Match PR

- `MatchStatsModal` displays stats from `/api/steam/match/{id}/`
- `SteamMatchLinker` stub calls `/api/steam/find-by-players/`
- `Game.gameid` links to Steam match ID

### Existing Components

- Uses `BaseNode`, `BaseHandle` from `~/components/ui/`
- Uses `Avatar`, `Badge`, `Button`, `Dialog`, `Table` from Shadcn UI
- Uses `useUserStore` for `isStaff()` and tournament data
- Integrates into existing `GamesTab.tsx`

---

## File Changes Summary

### New Files

```
frontend/app/
├── components/bracket/          # All bracket components (see structure above)
└── store/bracketStore.ts        # Bracket state management

backend/app/
└── (model updates only)
```

### Modified Files

```
frontend/app/
├── pages/tournament/tabs/GamesTab.tsx  # Add BracketView
└── package.json                         # Add elkjs dependency

backend/app/
├── models.py      # Add bracket fields to Game
├── serializers.py # Add BracketGameSerializer
├── views.py       # Add bracket endpoints
└── urls.py        # Add bracket routes
```

---

## Implementation Order

1. **Backend**: Add Game model fields, migrations, serializers, endpoints
2. **Types & Schemas**: Create types.ts and schemas.ts
3. **Utils**: Implement doubleElimination.ts, seeding.ts, bracketFactory.ts
4. **Store**: Create bracketStore.ts
5. **Layout**: Implement useElkLayout.ts hook
6. **Nodes**: Create MatchNode.tsx, EmptySlotNode.tsx
7. **Edges**: Create BracketEdge.tsx
8. **Controls**: Create BracketToolbar.tsx
9. **Modal**: Create MatchStatsModal.tsx
10. **Main View**: Create BracketView.tsx
11. **Integration**: Update GamesTab.tsx
12. **Swiss Stubs**: Add swissBracket.ts, SwissBracketView.tsx
13. **Testing**: E2E tests for bracket generation and interaction
