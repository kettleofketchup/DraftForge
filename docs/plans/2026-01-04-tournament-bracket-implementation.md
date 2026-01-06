# Tournament Bracket Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a React Flow tournament bracket component with double elimination support, auto-generation, and live polling.

**Architecture:** Frontend bracket visualization using React Flow with ELK.js layout, Zustand state management, and backend Game model extensions. Staff can generate/edit brackets, all users see live updates via polling.

**Tech Stack:** React Flow (@xyflow/react), ELK.js, Zustand, Zod, Django REST Framework, TailwindCSS, Shadcn UI

---

## Task 1: Backend Model Updates

**Files:**
- Modify: `backend/app/models.py`

**Step 1: Add bracket fields to Game model**

Add these fields after the existing `round` field in the `Game` class:

```python
    # Bracket positioning fields
    bracket_type = models.CharField(
        max_length=20,
        choices=[
            ('winners', 'Winners Bracket'),
            ('losers', 'Losers Bracket'),
            ('grand_finals', 'Grand Finals'),
        ],
        default='winners',
    )
    position = models.IntegerField(
        default=0,
        help_text="Position within round (0-indexed)"
    )

    # Match flow - which game winner advances to
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

    # Match status
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('live', 'Live'),
            ('completed', 'Completed'),
        ],
        default='pending',
    )
```

**Step 2: Create migration**

Run: `cd backend && source ../.venv/bin/activate && DISABLE_CACHE=true python manage.py makemigrations app --name add_bracket_fields_to_game`

Expected: Migration file created

**Step 3: Apply migration**

Run: `DISABLE_CACHE=true python manage.py migrate`

Expected: Migration applied successfully

**Step 4: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat(backend): add bracket fields to Game model"
```

---

## Task 2: Backend Serializers

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add BracketGameSerializer**

Add after existing GameSerializer:

```python
class BracketGameSerializer(serializers.ModelSerializer):
    """Serializer for bracket view with full team details."""
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


class BracketSaveSerializer(serializers.Serializer):
    """Serializer for saving bracket structure."""
    matches = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of match objects to save"
    )


class BracketGenerateSerializer(serializers.Serializer):
    """Serializer for generating bracket."""
    seeding_method = serializers.ChoiceField(
        choices=['random', 'mmr_total', 'captain_mmr'],
        default='mmr_total'
    )
```

**Step 2: Verify serializer imports**

Ensure `Game` and `TeamSerializer` are imported at top of file.

**Step 3: Commit**

```bash
git add backend/app/serializers.py
git commit -m "feat(backend): add bracket serializers"
```

---

## Task 3: Backend API Endpoints

**Files:**
- Create: `backend/app/views/bracket.py`
- Modify: `backend/app/urls.py`

**Step 1: Create bracket views file**

```python
"""Bracket API views for tournament bracket management."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from app.models import Game, Tournament, Team
from app.serializers import BracketGameSerializer, BracketSaveSerializer, BracketGenerateSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def get_bracket(request, tournament_id):
    """Get bracket structure for a tournament."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {'error': 'Tournament not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    games = Game.objects.filter(tournament=tournament).select_related(
        'radiant_team', 'dire_team', 'winning_team', 'next_game'
    ).order_by('bracket_type', 'round', 'position')

    serializer = BracketGameSerializer(games, many=True)
    return Response({
        'tournamentId': tournament_id,
        'matches': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_bracket(request, tournament_id):
    """Generate bracket structure from tournament teams."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {'error': 'Tournament not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = BracketGenerateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # TODO: Implement bracket generation logic
    # For now, return empty bracket structure
    return Response({
        'tournamentId': tournament_id,
        'matches': [],
        'message': 'Bracket generation placeholder'
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def save_bracket(request, tournament_id):
    """Save bracket structure to database."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {'error': 'Tournament not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = BracketSaveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # TODO: Implement bracket saving logic
    return Response({
        'tournamentId': tournament_id,
        'message': 'Bracket save placeholder'
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def advance_winner(request, game_id):
    """Mark winner and advance to next match."""
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {'error': 'Game not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    winner_slot = request.data.get('winner')  # 'radiant' or 'dire'
    if winner_slot not in ['radiant', 'dire']:
        return Response(
            {'error': 'Invalid winner slot'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Set winner
    if winner_slot == 'radiant':
        game.winning_team = game.radiant_team
    else:
        game.winning_team = game.dire_team
    game.status = 'completed'
    game.save()

    # Advance to next game if exists
    if game.next_game and game.next_game_slot:
        next_game = game.next_game
        if game.next_game_slot == 'radiant':
            next_game.radiant_team = game.winning_team
        else:
            next_game.dire_team = game.winning_team
        next_game.save()

    return Response(BracketGameSerializer(game).data)
```

**Step 2: Update urls.py**

Add to urlpatterns in `backend/app/urls.py`:

```python
from app.views.bracket import get_bracket, generate_bracket, save_bracket, advance_winner

# Add these paths:
path('tournaments/<int:tournament_id>/bracket/', get_bracket, name='get_bracket'),
path('tournaments/<int:tournament_id>/bracket/generate/', generate_bracket, name='generate_bracket'),
path('tournaments/<int:tournament_id>/bracket/save/', save_bracket, name='save_bracket'),
path('games/<int:game_id>/advance-winner/', advance_winner, name='advance_winner'),
```

**Step 3: Create views directory if needed**

Run: `mkdir -p backend/app/views && touch backend/app/views/__init__.py`

**Step 4: Commit**

```bash
git add backend/app/views/ backend/app/urls.py
git commit -m "feat(backend): add bracket API endpoints"
```

---

## Task 4: Frontend Types

**Files:**
- Create: `frontend/app/components/bracket/types.ts`

**Step 1: Create bracket directory**

Run: `mkdir -p frontend/app/components/bracket`

**Step 2: Create types file**

```typescript
import type { TeamType } from '~/components/tournament/types';

// Bracket section types
export type BracketSectionType = 'winners' | 'losers' | 'grand_finals';

// Match status
export type MatchStatus = 'pending' | 'live' | 'completed';

// Seeding methods
export type SeedingMethod = 'random' | 'mmr_total' | 'captain_mmr' | 'manual';

// Core match data for bracket display
export interface BracketMatch {
  id: string;                          // Temporary ID until persisted
  gameId?: number;                     // Backend Game.pk after save
  round: number;                       // Round number within bracket type
  position: number;                    // Position within round (0-indexed)
  bracketType: BracketSectionType;
  radiantTeam?: TeamType;
  direTeam?: TeamType;
  radiantScore?: number;
  direScore?: number;
  winner?: 'radiant' | 'dire';
  status: MatchStatus;
  steamMatchId?: number;               // Linked Steam match
  nextMatchId?: string;                // Winner advances to this match
  nextMatchSlot?: 'radiant' | 'dire';  // Which slot in next match
}

// Full bracket state
export interface BracketState {
  tournamentId: number;
  bracketType: 'double_elimination' | 'swiss';
  matches: BracketMatch[];
  isDirty: boolean;                    // Has unsaved changes
  isVirtual: boolean;                  // Not yet persisted to backend
}

// React Flow node data
export interface MatchNodeData extends BracketMatch {
  // Additional display properties can go here
}

export interface EmptySlotData {
  matchId: string;
  slot: 'radiant' | 'dire';
  roundLabel: string;
}

// API response types
export interface BracketResponse {
  tournamentId: number;
  matches: BracketMatch[];
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/
git commit -m "feat(frontend): add bracket TypeScript types"
```

---

## Task 5: Frontend Zod Schemas

**Files:**
- Create: `frontend/app/components/bracket/schemas.ts`

**Step 1: Create schemas file**

```typescript
import { z } from 'zod';

// Match status enum
export const MatchStatusSchema = z.enum(['pending', 'live', 'completed']);

// Bracket section enum
export const BracketSectionSchema = z.enum(['winners', 'losers', 'grand_finals']);

// Seeding method enum
export const SeedingMethodSchema = z.enum(['random', 'mmr_total', 'captain_mmr', 'manual']);

// Single bracket match
export const BracketMatchSchema = z.object({
  id: z.string(),
  gameId: z.number().optional(),
  round: z.number(),
  position: z.number(),
  bracketType: BracketSectionSchema,
  radiantTeamId: z.number().optional(),
  direTeamId: z.number().optional(),
  radiantScore: z.number().optional(),
  direScore: z.number().optional(),
  winnerId: z.number().optional(),
  status: MatchStatusSchema,
  steamMatchId: z.number().optional(),
  nextMatchId: z.string().optional(),
  nextMatchSlot: z.enum(['radiant', 'dire']).optional(),
});

// API response for bracket
export const BracketResponseSchema = z.object({
  tournamentId: z.number(),
  matches: z.array(BracketMatchSchema),
});

// Generate bracket request
export const GenerateBracketRequestSchema = z.object({
  seedingMethod: SeedingMethodSchema,
});

// Save bracket request
export const SaveBracketRequestSchema = z.object({
  matches: z.array(BracketMatchSchema),
});

// Type exports
export type BracketMatchInput = z.infer<typeof BracketMatchSchema>;
export type BracketResponseInput = z.infer<typeof BracketResponseSchema>;
```

**Step 2: Commit**

```bash
git add frontend/app/components/bracket/schemas.ts
git commit -m "feat(frontend): add bracket Zod schemas"
```

---

## Task 6: Double Elimination Generator

**Files:**
- Create: `frontend/app/components/bracket/utils/doubleElimination.ts`

**Step 1: Create utils directory**

Run: `mkdir -p frontend/app/components/bracket/utils`

**Step 2: Create double elimination generator**

```typescript
import type { BracketMatch, BracketSectionType } from '../types';
import type { TeamType } from '~/components/tournament/types';

/**
 * Generate a double elimination bracket structure.
 *
 * For N teams:
 * - Winners Bracket: ceil(log2(N)) rounds
 * - Losers Bracket: 2 * (ceil(log2(N)) - 1) rounds
 * - Grand Finals: 1-2 matches
 */
export function generateDoubleElimination(teams: TeamType[]): BracketMatch[] {
  const n = teams.length;
  if (n < 2) {
    throw new Error('Need at least 2 teams for a bracket');
  }

  const matches: BracketMatch[] = [];
  const winnersRounds = Math.ceil(Math.log2(n));

  // Pad to power of 2 for clean bracket
  const bracketSize = Math.pow(2, winnersRounds);

  let matchId = 1;

  // Generate Winners Bracket
  const winnersMatches = generateWinnersBracket(bracketSize, winnersRounds, matchId);
  matchId += winnersMatches.length;
  matches.push(...winnersMatches);

  // Generate Losers Bracket
  const losersRounds = 2 * (winnersRounds - 1);
  const losersMatches = generateLosersBracket(bracketSize, losersRounds, matchId, winnersMatches);
  matchId += losersMatches.length;
  matches.push(...losersMatches);

  // Generate Grand Finals
  const grandFinals = generateGrandFinals(matchId, winnersMatches, losersMatches);
  matches.push(...grandFinals);

  return matches;
}

function generateWinnersBracket(
  bracketSize: number,
  rounds: number,
  startId: number
): BracketMatch[] {
  const matches: BracketMatch[] = [];
  let matchId = startId;

  for (let round = 1; round <= rounds; round++) {
    const matchesInRound = bracketSize / Math.pow(2, round);

    for (let position = 0; position < matchesInRound; position++) {
      const match: BracketMatch = {
        id: `w-${matchId}`,
        round,
        position,
        bracketType: 'winners',
        status: 'pending',
      };

      // Set next match (winner advances)
      if (round < rounds) {
        const nextPosition = Math.floor(position / 2);
        const nextMatchId = matchId + matchesInRound - position + nextPosition;
        match.nextMatchId = `w-${nextMatchId}`;
        match.nextMatchSlot = position % 2 === 0 ? 'radiant' : 'dire';
      }

      matches.push(match);
      matchId++;
    }
  }

  return matches;
}

function generateLosersBracket(
  bracketSize: number,
  rounds: number,
  startId: number,
  winnersMatches: BracketMatch[]
): BracketMatch[] {
  const matches: BracketMatch[] = [];
  let matchId = startId;

  // Losers bracket has alternating "drop-down" and "elimination" rounds
  for (let round = 1; round <= rounds; round++) {
    // Calculate matches in this round
    const winnersRound = Math.ceil(round / 2);
    const isDropRound = round % 2 === 1;
    const matchesInRound = bracketSize / Math.pow(2, winnersRound + 1);

    for (let position = 0; position < matchesInRound; position++) {
      const match: BracketMatch = {
        id: `l-${matchId}`,
        round,
        position,
        bracketType: 'losers',
        status: 'pending',
      };

      // Set next match
      if (round < rounds) {
        const nextMatchId = matchId + matchesInRound;
        match.nextMatchId = `l-${nextMatchId}`;
        match.nextMatchSlot = position % 2 === 0 ? 'radiant' : 'dire';
      }

      matches.push(match);
      matchId++;
    }
  }

  return matches;
}

function generateGrandFinals(
  startId: number,
  winnersMatches: BracketMatch[],
  losersMatches: BracketMatch[]
): BracketMatch[] {
  const winnersFinalist = winnersMatches[winnersMatches.length - 1];
  const losersFinalist = losersMatches[losersMatches.length - 1];

  const grandFinals: BracketMatch = {
    id: `gf-${startId}`,
    round: 1,
    position: 0,
    bracketType: 'grand_finals',
    status: 'pending',
  };

  // Connect winners and losers finals to grand finals
  if (winnersFinalist) {
    winnersFinalist.nextMatchId = grandFinals.id;
    winnersFinalist.nextMatchSlot = 'radiant';
  }
  if (losersFinalist) {
    losersFinalist.nextMatchId = grandFinals.id;
    losersFinalist.nextMatchSlot = 'dire';
  }

  return [grandFinals];
}

/**
 * Get round label for display
 */
export function getRoundLabel(bracketType: BracketSectionType, round: number, totalRounds?: number): string {
  switch (bracketType) {
    case 'winners':
      if (totalRounds && round === totalRounds) return 'Winners Finals';
      if (totalRounds && round === totalRounds - 1) return 'Winners Semis';
      return `Winners R${round}`;
    case 'losers':
      if (totalRounds && round === totalRounds) return 'Losers Finals';
      return `Losers R${round}`;
    case 'grand_finals':
      return 'Grand Finals';
    default:
      return `Round ${round}`;
  }
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/utils/
git commit -m "feat(frontend): add double elimination bracket generator"
```

---

## Task 7: Seeding Utilities

**Files:**
- Create: `frontend/app/components/bracket/utils/seeding.ts`

**Step 1: Create seeding utilities**

```typescript
import type { TeamType } from '~/components/tournament/types';
import type { BracketMatch, SeedingMethod } from '../types';

/**
 * Get total MMR for a team (sum of all members)
 */
export function getTotalMMR(team: TeamType): number {
  const captainMMR = team.captain?.mmr ?? 0;
  const membersMMR = team.members?.reduce((sum, m) => sum + (m.mmr ?? 0), 0) ?? 0;
  return captainMMR + membersMMR;
}

/**
 * Sort teams by total MMR (highest first)
 */
export function seedByMMR(teams: TeamType[]): TeamType[] {
  return [...teams].sort((a, b) => getTotalMMR(b) - getTotalMMR(a));
}

/**
 * Sort teams by captain MMR (highest first)
 */
export function seedByCaptainMMR(teams: TeamType[]): TeamType[] {
  return [...teams].sort((a, b) => (b.captain?.mmr ?? 0) - (a.captain?.mmr ?? 0));
}

/**
 * Randomly shuffle teams
 */
export function seedRandom(teams: TeamType[]): TeamType[] {
  const shuffled = [...teams];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

/**
 * Apply seeding method to teams
 */
export function applySeedingMethod(teams: TeamType[], method: SeedingMethod): TeamType[] {
  switch (method) {
    case 'mmr_total':
      return seedByMMR(teams);
    case 'captain_mmr':
      return seedByCaptainMMR(teams);
    case 'random':
      return seedRandom(teams);
    case 'manual':
      return teams; // Keep original order
    default:
      return teams;
  }
}

/**
 * Standard bracket seeding pattern for first round.
 * For 8 teams: 1v8, 4v5, 2v7, 3v6
 * This ensures highest seeds don't meet until later rounds.
 */
export function getFirstRoundPairings(seededTeams: TeamType[]): [TeamType | undefined, TeamType | undefined][] {
  const n = seededTeams.length;
  const bracketSize = Math.pow(2, Math.ceil(Math.log2(n)));
  const pairings: [TeamType | undefined, TeamType | undefined][] = [];

  // Generate standard bracket positions
  const positions = generateBracketPositions(bracketSize);

  for (let i = 0; i < bracketSize / 2; i++) {
    const pos1 = positions[i * 2];
    const pos2 = positions[i * 2 + 1];
    pairings.push([
      seededTeams[pos1 - 1], // Seeds are 1-indexed
      seededTeams[pos2 - 1],
    ]);
  }

  return pairings;
}

/**
 * Generate standard bracket positions for a power-of-2 bracket size.
 * Returns array of seed numbers in bracket order.
 */
function generateBracketPositions(size: number): number[] {
  if (size === 2) return [1, 2];

  const half = generateBracketPositions(size / 2);
  const result: number[] = [];

  for (const seed of half) {
    result.push(seed);
    result.push(size + 1 - seed);
  }

  return result;
}

/**
 * Apply seeded teams to first round matches
 */
export function applyTeamsToFirstRound(
  matches: BracketMatch[],
  seededTeams: TeamType[]
): BracketMatch[] {
  const pairings = getFirstRoundPairings(seededTeams);
  const firstRoundMatches = matches.filter(
    (m) => m.bracketType === 'winners' && m.round === 1
  );

  return matches.map((match) => {
    if (match.bracketType === 'winners' && match.round === 1) {
      const pairing = pairings[match.position];
      if (pairing) {
        return {
          ...match,
          radiantTeam: pairing[0],
          direTeam: pairing[1],
        };
      }
    }
    return match;
  });
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/bracket/utils/seeding.ts
git commit -m "feat(frontend): add bracket seeding utilities"
```

---

## Task 8: Bracket Factory

**Files:**
- Create: `frontend/app/components/bracket/utils/bracketFactory.ts`

**Step 1: Create bracket factory**

```typescript
import type { TeamType } from '~/components/tournament/types';
import type { BracketMatch, SeedingMethod } from '../types';
import { generateDoubleElimination } from './doubleElimination';
import { applySeedingMethod, applyTeamsToFirstRound } from './seeding';

export type BracketType = 'double_elimination' | 'swiss';

export interface BracketResult {
  type: BracketType;
  matches: BracketMatch[];
}

/**
 * Factory function to generate bracket based on tournament type
 */
export function generateBracket(
  type: BracketType,
  teams: TeamType[],
  seedingMethod: SeedingMethod = 'mmr_total'
): BracketResult {
  switch (type) {
    case 'double_elimination': {
      // Seed teams first
      const seededTeams = applySeedingMethod(teams, seedingMethod);

      // Generate bracket structure
      const matches = generateDoubleElimination(seededTeams);

      // Apply teams to first round
      const matchesWithTeams = applyTeamsToFirstRound(matches, seededTeams);

      return {
        type: 'double_elimination',
        matches: matchesWithTeams,
      };
    }

    case 'swiss':
      // Stub for Swiss bracket - to be implemented later
      console.warn('Swiss bracket generation not yet implemented');
      return {
        type: 'swiss',
        matches: [],
      };

    default:
      throw new Error(`Unknown bracket type: ${type}`);
  }
}

/**
 * Reseed an existing bracket with a new seeding method
 */
export function reseedBracket(
  matches: BracketMatch[],
  teams: TeamType[],
  seedingMethod: SeedingMethod
): BracketMatch[] {
  // Clear existing team assignments
  const clearedMatches = matches.map((match) => ({
    ...match,
    radiantTeam: undefined,
    direTeam: undefined,
    winner: undefined,
    status: 'pending' as const,
  }));

  // Apply new seeding
  const seededTeams = applySeedingMethod(teams, seedingMethod);
  return applyTeamsToFirstRound(clearedMatches, seededTeams);
}
```

**Step 2: Create index file for utils**

```typescript
// frontend/app/components/bracket/utils/index.ts
export * from './doubleElimination';
export * from './seeding';
export * from './bracketFactory';
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/utils/
git commit -m "feat(frontend): add bracket factory and utils index"
```

---

## Task 9: ELK Layout Hook

**Files:**
- Create: `frontend/app/components/bracket/hooks/useElkLayout.ts`

**Step 1: Create hooks directory**

Run: `mkdir -p frontend/app/components/bracket/hooks`

**Step 2: Create ELK layout hook**

```typescript
import ELK from 'elkjs/lib/elk.bundled.js';
import { useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { BracketMatch } from '../types';

const elk = new ELK();

// ELK layout options for tournament bracket (left-to-right tree)
const defaultElkOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.spacing.nodeNode': '50',
  'elk.layered.spacing.nodeNodeBetweenLayers': '150',
  'elk.portConstraints': 'FIXED_ORDER',
  'elk.layered.nodePlacement.strategy': 'SIMPLE',
};

export interface LayoutConfig {
  nodeWidth?: number;
  nodeHeight?: number;
  options?: Record<string, string>;
}

export function useElkLayout() {
  const getLayoutedElements = useCallback(
    async (
      nodes: Node[],
      edges: Edge[],
      config: LayoutConfig = {}
    ): Promise<{ nodes: Node[]; edges: Edge[] }> => {
      const { nodeWidth = 208, nodeHeight = 100, options = {} } = config;

      const graph = {
        id: 'root',
        layoutOptions: { ...defaultElkOptions, ...options },
        children: nodes.map((node) => ({
          id: node.id,
          width: nodeWidth,
          height: nodeHeight,
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

      try {
        const layoutedGraph = await elk.layout(graph);

        const layoutedNodes = nodes.map((node) => {
          const elkNode = layoutedGraph.children?.find((n) => n.id === node.id);
          return {
            ...node,
            position: { x: elkNode?.x ?? 0, y: elkNode?.y ?? 0 },
          };
        });

        return { nodes: layoutedNodes, edges };
      } catch (error) {
        console.error('ELK layout failed:', error);
        // Return original nodes with default positions
        return {
          nodes: nodes.map((node, i) => ({
            ...node,
            position: { x: i * 250, y: i * 120 },
          })),
          edges,
        };
      }
    },
    []
  );

  return { getLayoutedElements };
}

/**
 * Layout double elimination bracket with separate sections
 */
export async function layoutDoubleElimination(
  matches: BracketMatch[],
  getLayoutedElements: ReturnType<typeof useElkLayout>['getLayoutedElements']
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  const BRACKET_GAP = 150;

  // Separate matches by bracket type
  const winnersMatches = matches.filter((m) => m.bracketType === 'winners');
  const losersMatches = matches.filter((m) => m.bracketType === 'losers');
  const grandFinalsMatches = matches.filter((m) => m.bracketType === 'grand_finals');

  // Convert to nodes
  const toNodes = (matches: BracketMatch[]): Node[] =>
    matches.map((match) => ({
      id: match.id,
      type: 'match',
      position: { x: 0, y: 0 },
      data: match,
    }));

  // Create edges from nextMatchId
  const toEdges = (matches: BracketMatch[]): Edge[] =>
    matches
      .filter((m) => m.nextMatchId)
      .map((match) => ({
        id: `${match.id}-${match.nextMatchId}`,
        source: match.id,
        target: match.nextMatchId!,
        type: 'bracket',
      }));

  // Layout winners bracket
  const winnersNodes = toNodes(winnersMatches);
  const winnersEdges = toEdges(winnersMatches);
  const winners = await getLayoutedElements(winnersNodes, winnersEdges);

  // Layout losers bracket
  const losersNodes = toNodes(losersMatches);
  const losersEdges = toEdges(losersMatches);
  const losers = await getLayoutedElements(losersNodes, losersEdges);

  // Calculate offset for losers bracket
  const winnersMaxY = Math.max(...winners.nodes.map((n) => n.position.y), 0);
  const losersOffset = winnersMaxY + BRACKET_GAP;

  // Apply offset to losers nodes
  const offsetLosers = losers.nodes.map((node) => ({
    ...node,
    position: { x: node.position.x, y: node.position.y + losersOffset },
  }));

  // Position grand finals
  const winnersMaxX = Math.max(...winners.nodes.map((n) => n.position.x), 0);
  const losersMaxX = Math.max(...offsetLosers.map((n) => n.position.x), 0);
  const grandFinalsX = Math.max(winnersMaxX, losersMaxX) + 250;
  const grandFinalsY = (winnersMaxY + losersOffset) / 2;

  const grandFinalsNodes: Node[] = grandFinalsMatches.map((match) => ({
    id: match.id,
    type: 'match',
    position: { x: grandFinalsX, y: grandFinalsY },
    data: match,
  }));

  // Combine all edges including cross-bracket connections
  const allEdges = [
    ...winners.edges,
    ...losers.edges,
    ...toEdges(grandFinalsMatches),
    // Winners final to grand finals
    ...winnersMatches
      .filter((m) => m.nextMatchId?.startsWith('gf-'))
      .map((m) => ({
        id: `${m.id}-${m.nextMatchId}`,
        source: m.id,
        target: m.nextMatchId!,
        type: 'bracket',
      })),
    // Losers final to grand finals
    ...losersMatches
      .filter((m) => m.nextMatchId?.startsWith('gf-'))
      .map((m) => ({
        id: `${m.id}-${m.nextMatchId}`,
        source: m.id,
        target: m.nextMatchId!,
        type: 'bracket',
      })),
  ];

  return {
    nodes: [...winners.nodes, ...offsetLosers, ...grandFinalsNodes],
    edges: allEdges,
  };
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/hooks/
git commit -m "feat(frontend): add ELK layout hook for bracket positioning"
```

---

## Task 10: Bracket Store (Zustand)

**Files:**
- Create: `frontend/app/store/bracketStore.ts`

**Step 1: Create bracket store**

```typescript
import { create } from 'zustand';
import type { Node, Edge } from '@xyflow/react';
import type { BracketMatch, SeedingMethod } from '~/components/bracket/types';
import type { TeamType } from '~/components/tournament/types';
import { generateBracket, reseedBracket } from '~/components/bracket/utils/bracketFactory';
import { api } from '~/components/api/axios';
import { BracketResponseSchema } from '~/components/bracket/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('bracketStore');

interface BracketStore {
  // State
  matches: BracketMatch[];
  nodes: Node[];
  edges: Edge[];
  isDirty: boolean;
  isVirtual: boolean;
  isLoading: boolean;
  pollInterval: ReturnType<typeof setInterval> | null;

  // Actions
  setMatches: (matches: BracketMatch[]) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;

  // Bracket operations
  generateBracket: (teams: TeamType[], method: SeedingMethod) => void;
  reseedBracket: (teams: TeamType[], method: SeedingMethod) => void;
  assignTeamToSlot: (matchId: string, slot: 'radiant' | 'dire', team: TeamType) => void;
  removeTeamFromSlot: (matchId: string, slot: 'radiant' | 'dire') => void;
  setMatchWinner: (matchId: string, winner: 'radiant' | 'dire') => void;
  advanceWinner: (matchId: string) => void;

  // Persistence
  saveBracket: (tournamentId: number) => Promise<void>;
  loadBracket: (tournamentId: number) => Promise<void>;
  resetBracket: () => void;

  // Polling
  startPolling: (tournamentId: number, intervalMs?: number) => void;
  stopPolling: () => void;
}

export const useBracketStore = create<BracketStore>()((set, get) => ({
  matches: [],
  nodes: [],
  edges: [],
  isDirty: false,
  isVirtual: true,
  isLoading: false,
  pollInterval: null,

  setMatches: (matches) => set({ matches, isDirty: true }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  generateBracket: (teams, method) => {
    log.debug('Generating bracket', { teams: teams.length, method });
    const result = generateBracket('double_elimination', teams, method);
    set({
      matches: result.matches,
      isDirty: true,
      isVirtual: true,
    });
  },

  reseedBracket: (teams, method) => {
    log.debug('Reseeding bracket', { method });
    const reseeded = reseedBracket(get().matches, teams, method);
    set({
      matches: reseeded,
      isDirty: true,
    });
  },

  assignTeamToSlot: (matchId, slot, team) => {
    log.debug('Assigning team to slot', { matchId, slot, team: team.name });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId
          ? { ...m, [slot === 'radiant' ? 'radiantTeam' : 'direTeam']: team }
          : m
      ),
      isDirty: true,
    }));
  },

  removeTeamFromSlot: (matchId, slot) => {
    log.debug('Removing team from slot', { matchId, slot });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId
          ? { ...m, [slot === 'radiant' ? 'radiantTeam' : 'direTeam']: undefined }
          : m
      ),
      isDirty: true,
    }));
  },

  setMatchWinner: (matchId, winner) => {
    log.debug('Setting match winner', { matchId, winner });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId ? { ...m, winner, status: 'completed' as const } : m
      ),
      isDirty: true,
    }));
  },

  advanceWinner: (matchId) => {
    const match = get().matches.find((m) => m.id === matchId);
    if (!match?.winner || !match.nextMatchId) return;

    const winningTeam =
      match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
    if (!winningTeam) return;

    log.debug('Advancing winner', { matchId, nextMatchId: match.nextMatchId });
    get().assignTeamToSlot(match.nextMatchId, match.nextMatchSlot!, winningTeam);
  },

  saveBracket: async (tournamentId) => {
    log.debug('Saving bracket', { tournamentId });
    set({ isLoading: true });
    try {
      await api.post(`/api/tournaments/${tournamentId}/bracket/save/`, {
        matches: get().matches,
      });
      set({ isDirty: false, isVirtual: false });
      log.debug('Bracket saved successfully');
    } catch (error) {
      log.error('Failed to save bracket', error);
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  loadBracket: async (tournamentId) => {
    log.debug('Loading bracket', { tournamentId });
    set({ isLoading: true });
    try {
      const response = await api.get(`/api/tournaments/${tournamentId}/bracket/`);
      const data = BracketResponseSchema.parse(response.data);

      if (data.matches.length > 0) {
        set({
          matches: data.matches as BracketMatch[],
          isDirty: false,
          isVirtual: false,
        });
        log.debug('Bracket loaded', { matchCount: data.matches.length });
      }
    } catch (error) {
      log.error('Failed to load bracket', error);
    } finally {
      set({ isLoading: false });
    }
  },

  resetBracket: () => {
    log.debug('Resetting bracket');
    set({
      matches: [],
      nodes: [],
      edges: [],
      isDirty: false,
      isVirtual: true,
    });
  },

  startPolling: (tournamentId, intervalMs = 5000) => {
    get().stopPolling();
    log.debug('Starting bracket polling', { tournamentId, intervalMs });

    const interval = setInterval(() => {
      // Only poll if not dirty (no unsaved changes)
      if (!get().isDirty) {
        get().loadBracket(tournamentId);
      }
    }, intervalMs);

    set({ pollInterval: interval });
  },

  stopPolling: () => {
    const interval = get().pollInterval;
    if (interval) {
      log.debug('Stopping bracket polling');
      clearInterval(interval);
      set({ pollInterval: null });
    }
  },
}));
```

**Step 2: Commit**

```bash
git add frontend/app/store/bracketStore.ts
git commit -m "feat(frontend): add Zustand bracket store"
```

---

## Task 11: Match Node Component

**Files:**
- Create: `frontend/app/components/bracket/nodes/MatchNode.tsx`

**Step 1: Create nodes directory**

Run: `mkdir -p frontend/app/components/bracket/nodes`

**Step 2: Create MatchNode component**

```typescript
import { memo } from 'react';
import { type NodeProps, Position } from '@xyflow/react';
import {
  BaseNode,
  BaseNodeHeader,
  BaseNodeHeaderTitle,
  BaseNodeContent,
} from '~/components/ui/base-node';
import { BaseHandle } from '~/components/ui/base-handle';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import type { BracketMatch, BracketSectionType } from '../types';
import type { TeamType } from '~/components/tournament/types';
import { getRoundLabel } from '../utils/doubleElimination';

const statusConfig = {
  pending: { label: 'Upcoming', className: 'bg-muted text-muted-foreground' },
  live: { label: 'LIVE', className: 'bg-red-500 text-white animate-pulse' },
  completed: { label: 'Final', className: 'bg-green-500/20 text-green-500' },
};

export const MatchNode = memo(({ data, selected }: NodeProps<BracketMatch>) => {
  const status = statusConfig[data.status];
  const roundLabel = getRoundLabel(data.bracketType, data.round);

  return (
    <BaseNode
      className={cn(
        'w-52 cursor-pointer transition-all',
        selected && 'ring-2 ring-primary'
      )}
    >
      {/* Left handle - receives winner from previous match */}
      <BaseHandle type="target" position={Position.Left} />

      {/* Header with round label and status */}
      <BaseNodeHeader className="border-b pb-2">
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
    </BaseNode>
  );
});

MatchNode.displayName = 'MatchNode';

interface TeamSlotProps {
  team?: TeamType;
  score?: number;
  isWinner: boolean;
  isCompleted: boolean;
}

function TeamSlot({ team, score, isWinner, isCompleted }: TeamSlotProps) {
  if (!team) {
    return (
      <div className="flex items-center gap-2 p-1.5 rounded bg-muted/50">
        <div className="h-6 w-6 rounded-full bg-muted" />
        <span className="text-xs text-muted-foreground italic">TBD</span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex items-center gap-2 p-1.5 rounded transition-colors',
        isWinner && isCompleted && 'bg-green-500/10',
        !isWinner && isCompleted && 'opacity-50'
      )}
    >
      {/* Team avatar */}
      <Avatar className="h-6 w-6">
        <AvatarImage src={team.captain?.avatarUrl} />
        <AvatarFallback className="text-xs">
          {team.name.substring(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>

      {/* Team name */}
      <span
        className={cn(
          'flex-1 text-sm truncate',
          isWinner && isCompleted && 'font-semibold'
        )}
      >
        {team.name}
      </span>

      {/* Score (if completed) */}
      {isCompleted && score !== undefined && (
        <span
          className={cn(
            'text-sm font-mono',
            isWinner ? 'text-green-500 font-bold' : 'text-muted-foreground'
          )}
        >
          {score}
        </span>
      )}

      {/* Winner indicator */}
      {isWinner && isCompleted && <span className="text-green-500">✓</span>}
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/nodes/
git commit -m "feat(frontend): add MatchNode component"
```

---

## Task 12: Empty Slot Node Component

**Files:**
- Create: `frontend/app/components/bracket/nodes/EmptySlotNode.tsx`

**Step 1: Create EmptySlotNode component**

```typescript
import { memo } from 'react';
import { type NodeProps, Position } from '@xyflow/react';
import { BaseNode, BaseNodeContent } from '~/components/ui/base-node';
import { BaseHandle } from '~/components/ui/base-handle';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { EmptySlotData } from '../types';

export const EmptySlotNode = memo(({ data }: NodeProps<EmptySlotData>) => {
  const isStaff = useUserStore((state) => state.isStaff());

  return (
    <BaseNode
      className={cn(
        'w-52 border-dashed',
        isStaff && 'cursor-pointer hover:border-primary/50'
      )}
    >
      <BaseHandle type="target" position={Position.Left} />

      <BaseNodeContent className="py-6">
        <div className="text-center text-muted-foreground text-sm">
          {isStaff ? 'Drop team here' : 'TBD'}
        </div>
        <div className="text-center text-xs text-muted-foreground/50">
          {data.roundLabel}
        </div>
      </BaseNodeContent>

      <BaseHandle type="source" position={Position.Right} />
    </BaseNode>
  );
});

EmptySlotNode.displayName = 'EmptySlotNode';
```

**Step 2: Create nodes index file**

```typescript
// frontend/app/components/bracket/nodes/index.ts
export { MatchNode } from './MatchNode';
export { EmptySlotNode } from './EmptySlotNode';
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/nodes/
git commit -m "feat(frontend): add EmptySlotNode component"
```

---

## Task 13: Bracket Edge Component

**Files:**
- Create: `frontend/app/components/bracket/edges/BracketEdge.tsx`

**Step 1: Create edges directory**

Run: `mkdir -p frontend/app/components/bracket/edges`

**Step 2: Create BracketEdge component**

```typescript
import { memo } from 'react';
import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react';

interface BracketEdgeData {
  isWinnerPath?: boolean;
  isLoserPath?: boolean;
}

export const BracketEdge = memo(
  ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    style,
  }: EdgeProps<BracketEdgeData>) => {
    const [edgePath] = getSmoothStepPath({
      sourceX,
      sourceY,
      targetX,
      targetY,
      sourcePosition,
      targetPosition,
      borderRadius: 8,
    });

    return (
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          strokeWidth: data?.isWinnerPath ? 3 : 2,
          stroke: data?.isWinnerPath
            ? 'rgb(34 197 94)' // green-500
            : data?.isLoserPath
              ? 'rgb(239 68 68)' // red-500
              : 'rgb(148 163 184)', // slate-400
        }}
      />
    );
  }
);

BracketEdge.displayName = 'BracketEdge';
```

**Step 3: Create edges index file**

```typescript
// frontend/app/components/bracket/edges/index.ts
export { BracketEdge } from './BracketEdge';
```

**Step 4: Commit**

```bash
git add frontend/app/components/bracket/edges/
git commit -m "feat(frontend): add BracketEdge component"
```

---

## Task 14: Bracket Toolbar Component

**Files:**
- Create: `frontend/app/components/bracket/controls/BracketToolbar.tsx`

**Step 1: Create controls directory**

Run: `mkdir -p frontend/app/components/bracket/controls`

**Step 2: Create BracketToolbar component**

```typescript
import { useState } from 'react';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import { useBracketStore } from '~/store/bracketStore';
import type { TeamType } from '~/components/tournament/types';
import type { SeedingMethod } from '../types';

interface BracketToolbarProps {
  tournamentId: number;
  teams: TeamType[];
  hasMatches: boolean;
  isDirty: boolean;
  isVirtual: boolean;
}

export function BracketToolbar({
  tournamentId,
  teams,
  hasMatches,
  isDirty,
  isVirtual,
}: BracketToolbarProps) {
  const { generateBracket, reseedBracket, saveBracket, resetBracket, isLoading } =
    useBracketStore();

  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showGenerateConfirm, setShowGenerateConfirm] = useState(false);
  const [pendingSeedMethod, setPendingSeedMethod] = useState<SeedingMethod | null>(
    null
  );

  const handleGenerate = (method: SeedingMethod) => {
    if (hasMatches) {
      setPendingSeedMethod(method);
      setShowGenerateConfirm(true);
    } else {
      generateBracket(teams, method);
    }
  };

  const confirmGenerate = () => {
    if (pendingSeedMethod) {
      generateBracket(teams, pendingSeedMethod);
    }
    setShowGenerateConfirm(false);
    setPendingSeedMethod(null);
  };

  const handleSave = () => {
    saveBracket(tournamentId);
  };

  const handleReset = () => {
    resetBracket();
    setShowResetConfirm(false);
  };

  const minTeamsForBracket = 2;
  const canGenerate = teams.length >= minTeamsForBracket;

  return (
    <div className="flex items-center gap-2 mb-4 p-2 bg-base-200 rounded-lg">
      {/* Generate / Reseed dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" disabled={!canGenerate}>
            {hasMatches ? 'Reseed Bracket' : 'Generate Bracket'}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => handleGenerate('mmr_total')}>
            Seed by Team MMR (Recommended)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleGenerate('captain_mmr')}>
            Seed by Captain MMR
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => handleGenerate('random')}>
            Random Seeding
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Save button */}
      {hasMatches && (
        <Button
          onClick={handleSave}
          disabled={!isDirty || isLoading}
          variant={isDirty ? 'default' : 'outline'}
        >
          {isLoading ? 'Saving...' : isVirtual ? 'Save Bracket' : 'Save Changes'}
        </Button>
      )}

      {/* Reset button */}
      {hasMatches && (
        <Button variant="destructive" onClick={() => setShowResetConfirm(true)}>
          Reset
        </Button>
      )}

      {/* Team count indicator */}
      <span className="ml-auto text-sm text-muted-foreground">
        {teams.length} teams
      </span>

      {/* Generate confirmation dialog */}
      <AlertDialog open={showGenerateConfirm} onOpenChange={setShowGenerateConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate Bracket?</AlertDialogTitle>
            <AlertDialogDescription>
              This will replace the current bracket structure. Any unsaved changes
              will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmGenerate}>
              Regenerate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset confirmation dialog */}
      <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Bracket?</AlertDialogTitle>
            <AlertDialogDescription>
              This will clear all matches. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleReset} className="bg-destructive">
              Reset
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

**Step 3: Create controls index file**

```typescript
// frontend/app/components/bracket/controls/index.ts
export { BracketToolbar } from './BracketToolbar';
```

**Step 4: Commit**

```bash
git add frontend/app/components/bracket/controls/
git commit -m "feat(frontend): add BracketToolbar component"
```

---

## Task 15: Match Stats Modal

**Files:**
- Create: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**Step 1: Create modals directory**

Run: `mkdir -p frontend/app/components/bracket/modals`

**Step 2: Create MatchStatsModal component**

```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { useBracketStore } from '~/store/bracketStore';
import type { BracketMatch } from '../types';
import type { TeamType } from '~/components/tournament/types';
import { getRoundLabel } from '../utils/doubleElimination';

interface MatchStatsModalProps {
  match?: BracketMatch;
  open: boolean;
  onClose: () => void;
}

export function MatchStatsModal({ match, open, onClose }: MatchStatsModalProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const { setMatchWinner, advanceWinner } = useBracketStore();

  if (!match) return null;

  const hasLinkedSteamMatch = !!match.steamMatchId;
  const isCompleted = match.status === 'completed';

  const handleSetWinner = (winner: 'radiant' | 'dire') => {
    setMatchWinner(match.id, winner);
    advanceWinner(match.id);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span>{match.radiantTeam?.name ?? 'TBD'}</span>
            <span className="text-muted-foreground">vs</span>
            <span>{match.direTeam?.name ?? 'TBD'}</span>
            <Badge variant="outline" className="ml-auto">
              {getRoundLabel(match.bracketType, match.round)}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="overview">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="stats" disabled={!hasLinkedSteamMatch}>
              Player Stats
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4">
            <MatchOverview match={match} />

            {/* Staff controls for setting winner */}
            {isStaff && !isCompleted && match.radiantTeam && match.direTeam && (
              <div className="border-t pt-4">
                <p className="text-sm text-muted-foreground mb-3">
                  Select match winner:
                </p>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1 h-auto py-3"
                    onClick={() => handleSetWinner('radiant')}
                  >
                    <TeamDisplay team={match.radiantTeam} />
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1 h-auto py-3"
                    onClick={() => handleSetWinner('dire')}
                  >
                    <TeamDisplay team={match.direTeam} />
                  </Button>
                </div>
              </div>
            )}

            {/* Steam match link placeholder */}
            {isStaff && !hasLinkedSteamMatch && (
              <div className="border-t pt-4">
                <p className="text-sm text-muted-foreground mb-2">
                  Link Steam Match (coming soon)
                </p>
                <Button variant="outline" disabled>
                  Find Matching Steam Games
                </Button>
              </div>
            )}
          </TabsContent>

          {/* Player Stats Tab - placeholder for Steam integration */}
          <TabsContent value="stats">
            <div className="text-center text-muted-foreground py-8">
              {hasLinkedSteamMatch
                ? 'Loading stats from Steam...'
                : 'No Steam match linked'}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function MatchOverview({ match }: { match: BracketMatch }) {
  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Radiant team */}
      <div
        className={cn(
          'p-4 rounded-lg border',
          match.winner === 'radiant' && 'bg-green-500/10 border-green-500'
        )}
      >
        <div className="flex items-center gap-2 mb-3">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span className="text-sm text-muted-foreground">Radiant</span>
          {match.winner === 'radiant' && (
            <Badge className="ml-auto bg-green-500">Winner</Badge>
          )}
        </div>
        {match.radiantTeam ? (
          <TeamCard team={match.radiantTeam} />
        ) : (
          <div className="text-muted-foreground italic">TBD</div>
        )}
      </div>

      {/* Dire team */}
      <div
        className={cn(
          'p-4 rounded-lg border',
          match.winner === 'dire' && 'bg-green-500/10 border-green-500'
        )}
      >
        <div className="flex items-center gap-2 mb-3">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <span className="text-sm text-muted-foreground">Dire</span>
          {match.winner === 'dire' && (
            <Badge className="ml-auto bg-green-500">Winner</Badge>
          )}
        </div>
        {match.direTeam ? (
          <TeamCard team={match.direTeam} />
        ) : (
          <div className="text-muted-foreground italic">TBD</div>
        )}
      </div>
    </div>
  );
}

function TeamCard({ team }: { team: TeamType }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Avatar>
          <AvatarImage src={team.captain?.avatarUrl} />
          <AvatarFallback>{team.name.substring(0, 2)}</AvatarFallback>
        </Avatar>
        <div>
          <div className="font-semibold">{team.name}</div>
          <div className="text-xs text-muted-foreground">
            Captain: {team.captain?.nickname ?? team.captain?.username}
          </div>
        </div>
      </div>
      {/* Team members */}
      <div className="flex flex-wrap gap-1">
        {team.members?.map((member) => (
          <Avatar key={member.pk} className="h-6 w-6">
            <AvatarImage src={member.avatarUrl} />
            <AvatarFallback className="text-xs">
              {member.username?.substring(0, 1)}
            </AvatarFallback>
          </Avatar>
        ))}
      </div>
    </div>
  );
}

function TeamDisplay({ team }: { team: TeamType }) {
  return (
    <div className="flex items-center gap-2">
      <Avatar className="h-8 w-8">
        <AvatarImage src={team.captain?.avatarUrl} />
        <AvatarFallback>{team.name.substring(0, 2)}</AvatarFallback>
      </Avatar>
      <span>{team.name}</span>
    </div>
  );
}
```

**Step 3: Create modals index file**

```typescript
// frontend/app/components/bracket/modals/index.ts
export { MatchStatsModal } from './MatchStatsModal';
```

**Step 4: Commit**

```bash
git add frontend/app/components/bracket/modals/
git commit -m "feat(frontend): add MatchStatsModal component"
```

---

## Task 16: Main BracketView Component

**Files:**
- Create: `frontend/app/components/bracket/BracketView.tsx`

**Step 1: Create BracketView component**

```typescript
import { useCallback, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type OnNodesChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useBracketStore } from '~/store/bracketStore';
import { useUserStore } from '~/store/userStore';
import { useElkLayout, layoutDoubleElimination } from './hooks/useElkLayout';
import { MatchNode } from './nodes/MatchNode';
import { EmptySlotNode } from './nodes/EmptySlotNode';
import { BracketEdge } from './edges/BracketEdge';
import { BracketToolbar } from './controls/BracketToolbar';
import { MatchStatsModal } from './modals/MatchStatsModal';
import type { BracketMatch } from './types';

// Register node/edge types outside component to prevent re-renders
const nodeTypes = {
  match: MatchNode,
  emptySlot: EmptySlotNode,
};

const edgeTypes = {
  bracket: BracketEdge,
};

interface BracketViewProps {
  tournamentId: number;
}

export function BracketView({ tournamentId }: BracketViewProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const tournament = useUserStore((state) => state.tournament);

  const {
    matches,
    isDirty,
    isVirtual,
    isLoading,
    setNodes: setStoreNodes,
    setEdges: setStoreEdges,
    loadBracket,
    startPolling,
    stopPolling,
  } = useBracketStore();

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const { getLayoutedElements } = useElkLayout();

  // Selected match for stats modal
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const selectedMatch = matches.find((m) => m.id === selectedMatchId);

  // Load bracket on mount
  useEffect(() => {
    loadBracket(tournamentId);
    return () => stopPolling();
  }, [tournamentId, loadBracket, stopPolling]);

  // Start polling for live updates (when not editing)
  useEffect(() => {
    if (!isDirty) {
      startPolling(tournamentId, 5000);
    } else {
      stopPolling();
    }
    return () => stopPolling();
  }, [isDirty, tournamentId, startPolling, stopPolling]);

  // Re-layout when matches change
  useEffect(() => {
    async function layout() {
      if (matches.length === 0) return;

      const { nodes: layoutedNodes, edges: layoutedEdges } =
        await layoutDoubleElimination(matches, getLayoutedElements);

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
      setStoreNodes(layoutedNodes);
      setStoreEdges(layoutedEdges);
    }
    layout();
  }, [matches, getLayoutedElements, setNodes, setEdges, setStoreNodes, setStoreEdges]);

  // Handle node drag (staff only)
  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (!isStaff) {
        // Filter out position changes for non-staff
        changes = changes.filter((c) => c.type !== 'position');
      }
      onNodesChange(changes);
    },
    [isStaff, onNodesChange]
  );

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedMatchId(node.id);
  }, []);

  if (isLoading && matches.length === 0) {
    return (
      <div className="flex items-center justify-center h-96">
        Loading bracket...
      </div>
    );
  }

  const teams = tournament?.teams ?? [];

  return (
    <div className="h-[600px] w-full">
      {/* Staff toolbar */}
      {isStaff && (
        <BracketToolbar
          tournamentId={tournamentId}
          teams={teams}
          hasMatches={matches.length > 0}
          isDirty={isDirty}
          isVirtual={isVirtual}
        />
      )}

      {/* Dirty indicator */}
      {isDirty && (
        <div className="bg-yellow-500/10 text-yellow-500 text-sm px-3 py-1 rounded mb-2">
          Unsaved changes
        </div>
      )}

      {/* Empty state */}
      {matches.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-96 text-muted-foreground">
          <p className="mb-4">No bracket generated yet.</p>
          {isStaff && teams.length >= 2 && (
            <p className="text-sm">
              Use the toolbar above to generate a bracket.
            </p>
          )}
          {teams.length < 2 && (
            <p className="text-sm">Need at least 2 teams to create a bracket.</p>
          )}
        </div>
      )}

      {/* React Flow canvas */}
      {matches.length > 0 && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={isStaff}
          nodesConnectable={false}
          elementsSelectable={true}
        >
          <Background />
          <Controls />
        </ReactFlow>
      )}

      {/* Match stats modal */}
      <MatchStatsModal
        match={selectedMatch}
        open={!!selectedMatchId}
        onClose={() => setSelectedMatchId(null)}
      />
    </div>
  );
}
```

**Step 2: Create component index file**

```typescript
// frontend/app/components/bracket/index.ts
export { BracketView } from './BracketView';
export * from './types';
export * from './schemas';
```

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/BracketView.tsx frontend/app/components/bracket/index.ts
git commit -m "feat(frontend): add main BracketView component"
```

---

## Task 17: Integrate into GamesTab

**Files:**
- Modify: `frontend/app/pages/tournament/tabs/GamesTab.tsx`

**Step 1: Update GamesTab to include BracketView**

Replace the contents of GamesTab.tsx:

```typescript
import { memo, useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { BracketView } from '~/components/bracket';
import { GameCreateModal } from '~/components/game/create/createGameModal';
import { GameCard } from '~/components/game/gameCard/gameCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('GamesTab');

export const GamesTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const isStaff = useUserStore((state) => state.isStaff());
  const [viewMode, setViewMode] = useState<'bracket' | 'list'>('bracket');

  const renderNoGames = () => {
    return (
      <div className="flex justify-center items-center h-40">
        <div className="alert alert-info">
          <span>No games available for this tournament.</span>
        </div>
      </div>
    );
  };

  const renderGamesList = () => {
    if (!tournament || !tournament.games) {
      log.error('No Tournament games');
      return renderNoGames();
    }
    log.debug('rendering games');
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tournament.games?.map((game) => (
          <GameCard key={game.pk} game={game} />
        ))}
      </div>
    );
  };

  return (
    <div className="py-5 px-3 mx-auto container bg-base-300 rounded-lg shadow-lg">
      {/* View mode tabs */}
      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'bracket' | 'list')}>
        <div className="flex items-center justify-between mb-4">
          <TabsList>
            <TabsTrigger value="bracket">Bracket View</TabsTrigger>
            <TabsTrigger value="list">List View</TabsTrigger>
          </TabsList>

          {isStaff && viewMode === 'list' && (
            <GameCreateModal data-testid="gameCreateModalBtn" />
          )}
        </div>

        <TabsContent value="bracket">
          {tournament?.pk ? (
            <BracketView tournamentId={tournament.pk} />
          ) : (
            <div className="text-center text-muted-foreground py-8">
              No tournament selected
            </div>
          )}
        </TabsContent>

        <TabsContent value="list">
          {!tournament || !tournament.games || tournament.games.length === 0
            ? renderNoGames()
            : renderGamesList()}
        </TabsContent>
      </Tabs>
    </div>
  );
});
```

**Step 2: Commit**

```bash
git add frontend/app/pages/tournament/tabs/GamesTab.tsx
git commit -m "feat(frontend): integrate BracketView into GamesTab"
```

---

## Task 18: Swiss Bracket Stubs

**Files:**
- Create: `frontend/app/components/bracket/utils/swissBracket.ts`
- Create: `frontend/app/components/bracket/views/SwissBracketView.tsx`

**Step 1: Create Swiss bracket utilities (stub)**

```typescript
// frontend/app/components/bracket/utils/swissBracket.ts
import type { BracketMatch } from '../types';
import type { TeamType } from '~/components/tournament/types';

/**
 * Swiss bracket configuration
 */
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

/**
 * Generate Swiss bracket structure (STUB)
 */
export function generateSwissBracket(config: SwissConfig): SwissRound[] {
  console.warn('Swiss bracket generation not yet implemented');
  return [];
}

/**
 * Generate pairings for next Swiss round (STUB)
 */
export function generateSwissPairings(
  standings: SwissStanding[],
  previousMatches: BracketMatch[]
): BracketMatch[] {
  console.warn('Swiss pairing generation not yet implemented');
  return [];
}

/**
 * Calculate updated standings after a round (STUB)
 */
export function calculateSwissStandings(
  currentStandings: SwissStanding[],
  completedMatches: BracketMatch[],
  config: SwissConfig
): SwissStanding[] {
  console.warn('Swiss standings calculation not yet implemented');
  return currentStandings;
}

/**
 * Check if Swiss bracket is complete
 */
export function isSwissComplete(
  standings: SwissStanding[],
  config: SwissConfig
): boolean {
  const activeTeams = standings.filter((s) => s.status === 'active');
  return activeTeams.length === 0;
}

/**
 * Get teams that advanced from Swiss to playoffs
 */
export function getSwissAdvancers(standings: SwissStanding[]): TeamType[] {
  return standings.filter((s) => s.status === 'advanced').map((s) => s.team);
}
```

**Step 2: Create Swiss bracket view (stub)**

Run: `mkdir -p frontend/app/components/bracket/views`

```typescript
// frontend/app/components/bracket/views/SwissBracketView.tsx
import { memo } from 'react';
import { Badge } from '~/components/ui/badge';

interface SwissBracketViewProps {
  tournamentId: number;
}

/**
 * Swiss bracket view - STUB for future implementation
 */
export const SwissBracketView = memo(({ tournamentId }: SwissBracketViewProps) => {
  return (
    <div className="flex flex-col items-center justify-center h-96 text-muted-foreground">
      <Badge variant="outline" className="mb-4">Coming Soon</Badge>
      <p>Swiss bracket view is not yet implemented.</p>
      <p className="text-sm mt-2">Tournament ID: {tournamentId}</p>
    </div>
  );
});

SwissBracketView.displayName = 'SwissBracketView';
```

**Step 3: Update utils index**

Add to `frontend/app/components/bracket/utils/index.ts`:

```typescript
export * from './swissBracket';
```

**Step 4: Commit**

```bash
git add frontend/app/components/bracket/utils/swissBracket.ts frontend/app/components/bracket/views/
git commit -m "feat(frontend): add Swiss bracket stubs"
```

---

## Task 19: Final Cleanup and Testing

**Step 1: Create hooks index file**

```typescript
// frontend/app/components/bracket/hooks/index.ts
export * from './useElkLayout';
```

**Step 2: Update main bracket index**

```typescript
// frontend/app/components/bracket/index.ts
export { BracketView } from './BracketView';
export * from './types';
export * from './schemas';
export * from './nodes';
export * from './edges';
export * from './controls';
export * from './modals';
export * from './hooks';
export * from './utils';
```

**Step 3: Verify build compiles**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: Build completes (may have warnings but no errors related to bracket)

**Step 4: Final commit**

```bash
git add frontend/app/components/bracket/
git commit -m "feat(frontend): finalize bracket component structure"
```

---

## Task 20: Summary Commit

**Step 1: Create a summary commit with all changes**

Run: `git log --oneline -15` to see all commits

**Step 2: Verify branch is ready**

Run: `git status`

Expected: Clean working tree

Run: `git log main..HEAD --oneline`

Expected: Shows all bracket implementation commits

---

## Verification Checklist

After implementation, verify:

- [ ] Backend migration applied successfully
- [ ] `/api/tournaments/{id}/bracket/` returns empty bracket for new tournament
- [ ] Frontend builds without bracket-related errors
- [ ] BracketView renders in GamesTab
- [ ] Staff can see "Generate Bracket" button
- [ ] Bracket generates when clicked (appears in React Flow)
- [ ] Nodes are positioned correctly via ELK
- [ ] Clicking a match opens the stats modal
- [ ] Save button persists bracket to backend
- [ ] Polling updates bracket when changes occur
