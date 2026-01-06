# Match Stats Display Design

**Date**: 2026-01-05
**Status**: Draft
**Scope**: Frontend hero data integration + match stats modal for tournament bracket

## Overview

Add hero icons and match statistics display to the tournament bracket. When a bracket match has a linked Steam match, show compact hero icons on the bracket node and a full Dotabuff-style stats table in a modal on click.

## Goals

1. Display hero icons inline on bracket match nodes
2. Show detailed player statistics in a modal (Dotabuff-style table)
3. Use `dotaconstants` npm package for hero metadata
4. Integrate with existing Steam match data from `PlayerMatchStats` model

## Non-Goals

- Item display (future enhancement)
- Net worth tracking (not in current model)
- Ward placement stats (not in current model)

---

## Architecture

### Data Flow

```
dotaconstants (npm) → heroes.ts → HeroIconRow / PlayerStatsTable
                                         ↓
Backend API → useMatchStats hook → MatchStatsModal
```

### File Structure

```
frontend/app/
├── lib/dota/
│   ├── heroes.ts          # Hero lookup from dotaconstants
│   ├── schemas.ts         # Zod schemas for match data
│   └── utils.ts           # Formatting helpers
├── hooks/
│   └── useMatchStats.ts   # Match data fetching hook
└── components/bracket/
    ├── nodes/
    │   ├── MatchNode.tsx      # Updated with hero icons + modal trigger
    │   └── HeroIconRow.tsx    # Compact hero icon display
    └── modals/
        ├── MatchStatsModal.tsx    # Main modal wrapper
        └── PlayerStatsTable.tsx   # Dotabuff-style stats table
```

---

## Dependencies

```bash
npm add dotaconstants
```

The `dotaconstants` package provides hero metadata including `id`, `localized_name`, `img`, and `icon` URLs. Updates with each Dota patch via `npm update`.

---

## Data Layer

### Hero Lookup (`lib/dota/heroes.ts`)

```typescript
import heroesData from 'dotaconstants/build/heroes.json';

export interface DotaHero {
  id: number;
  name: string;           // "npc_dota_hero_antimage"
  localized_name: string; // "Anti-Mage"
  img: string;            // Full portrait URL
  icon: string;           // Small icon URL
  primary_attr: 'str' | 'agi' | 'int' | 'all';
}

export const heroes: Record<number, DotaHero> = heroesData;

export function getHero(heroId: number): DotaHero | undefined {
  return heroes[heroId];
}

export function getHeroIcon(heroId: number): string {
  return heroes[heroId]?.icon ?? '/placeholder-hero.png';
}

export function getHeroName(heroId: number): string {
  return heroes[heroId]?.localized_name ?? 'Unknown Hero';
}
```

### Zod Schemas (`lib/dota/schemas.ts`)

```typescript
import { z } from 'zod';

export const PlayerMatchStatsSchema = z.object({
  steam_id: z.number(),
  username: z.string().nullable(),
  player_slot: z.number(),
  hero_id: z.number(),
  kills: z.number(),
  deaths: z.number(),
  assists: z.number(),
  gold_per_min: z.number(),
  xp_per_min: z.number(),
  last_hits: z.number(),
  denies: z.number(),
  hero_damage: z.number(),
  tower_damage: z.number(),
  hero_healing: z.number(),
});

export const MatchDetailSchema = z.object({
  match_id: z.number(),
  radiant_win: z.boolean(),
  duration: z.number(),
  start_time: z.number(),
  game_mode: z.number(),
  lobby_type: z.number(),
  players: z.array(PlayerMatchStatsSchema),
});

export type PlayerMatchStats = z.infer<typeof PlayerMatchStatsSchema>;
export type MatchDetail = z.infer<typeof MatchDetailSchema>;
```

### Utility Functions (`lib/dota/utils.ts`)

```typescript
import type { PlayerMatchStats } from './schemas';

export function splitPlayersByTeam(players: PlayerMatchStats[]) {
  return {
    radiant: players.filter((p) => p.player_slot < 128),
    dire: players.filter((p) => p.player_slot >= 128),
  };
}

export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function formatMatchDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatNumber(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toString();
}
```

---

## Backend API

### Serializers (`backend/steam/serializers.py`)

```python
from rest_framework import serializers
from .models import Match, PlayerMatchStats


class PlayerMatchStatsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = PlayerMatchStats
        fields = [
            'steam_id',
            'username',
            'player_slot',
            'hero_id',
            'kills',
            'deaths',
            'assists',
            'gold_per_min',
            'xp_per_min',
            'last_hits',
            'denies',
            'hero_damage',
            'tower_damage',
            'hero_healing',
        ]


class MatchDetailSerializer(serializers.ModelSerializer):
    players = PlayerMatchStatsSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = [
            'match_id',
            'radiant_win',
            'duration',
            'start_time',
            'game_mode',
            'lobby_type',
            'players',
        ]
```

### View (`backend/steam/views.py`)

```python
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from .models import Match
from .serializers import MatchDetailSerializer


class MatchDetailView(RetrieveAPIView):
    queryset = Match.objects.prefetch_related('players__user')
    serializer_class = MatchDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'match_id'
```

### URL (`backend/steam/urls.py`)

```python
path('matches/<int:match_id>/', MatchDetailView.as_view(), name='match-detail'),
```

---

## Frontend Components

### Query Hook (`hooks/useMatchStats.ts`)

```typescript
import { useSuspenseQuery } from '@tanstack/react-query';
import { MatchDetailSchema, type MatchDetail } from '~/lib/dota/schemas';

async function fetchMatch(matchId: number): Promise<MatchDetail> {
  const response = await fetch(`/api/steam/matches/${matchId}/`);
  if (!response.ok) {
    throw new Error(`Failed to fetch match: ${response.status}`);
  }
  const data = await response.json();
  return MatchDetailSchema.parse(data);
}

export function useMatchStats(matchId: number | null) {
  return useSuspenseQuery({
    queryKey: ['match', matchId],
    queryFn: () => fetchMatch(matchId!),
    enabled: matchId !== null,
  });
}
```

### HeroIconRow (`components/bracket/nodes/HeroIconRow.tsx`)

Compact row of 5 hero icons for display on bracket nodes.

```typescript
import { getHeroIcon, getHeroName } from '~/lib/dota/heroes';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

interface HeroIconRowProps {
  heroIds: number[];
  isWinner?: boolean;
}

export function HeroIconRow({ heroIds, isWinner }: HeroIconRowProps) {
  return (
    <div className={cn(
      "flex gap-0.5",
      isWinner && "ring-1 ring-green-500 rounded"
    )}>
      {heroIds.map((heroId) => (
        <Tooltip key={heroId}>
          <TooltipTrigger>
            <img
              src={getHeroIcon(heroId)}
              alt={getHeroName(heroId)}
              className="w-5 h-5 rounded-sm"
            />
          </TooltipTrigger>
          <TooltipContent>{getHeroName(heroId)}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
```

### PlayerStatsTable (`components/bracket/modals/PlayerStatsTable.tsx`)

Dotabuff-style stats table with color-coded columns.

```typescript
import { getHeroIcon, getHeroName } from '~/lib/dota/heroes';
import { formatNumber } from '~/lib/dota/utils';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '~/components/ui/table';
import { cn } from '~/lib/utils';
import type { PlayerMatchStats } from '~/lib/dota/schemas';

interface PlayerStatsTableProps {
  players: PlayerMatchStats[];
  team: 'Radiant' | 'Dire';
  isWinner: boolean;
}

export function PlayerStatsTable({ players, team, isWinner }: PlayerStatsTableProps) {
  const totals = players.reduce(
    (acc, p) => ({
      kills: acc.kills + p.kills,
      deaths: acc.deaths + p.deaths,
      assists: acc.assists + p.assists,
    }),
    { kills: 0, deaths: 0, assists: 0 }
  );

  return (
    <div className="space-y-2">
      {/* Team Header */}
      <div className={cn(
        "flex items-center justify-between px-3 py-2 rounded",
        isWinner ? "bg-green-900/30" : "bg-red-900/30"
      )}>
        <div className="flex items-center gap-2">
          <span className={cn(
            "font-semibold uppercase",
            team === 'Radiant' ? "text-green-400" : "text-red-400"
          )}>
            {team}
          </span>
          {isWinner && (
            <span className="text-xs bg-green-600 px-1.5 py-0.5 rounded">
              Victory
            </span>
          )}
        </div>
        <span className="text-muted-foreground text-sm">
          {totals.kills} / {totals.deaths} / {totals.assists}
        </span>
      </div>

      <Table>
        <TableHeader>
          <TableRow className="text-xs">
            <TableHead className="w-10">Hero</TableHead>
            <TableHead>Player</TableHead>
            <TableHead className="text-center w-8">K</TableHead>
            <TableHead className="text-center w-8">D</TableHead>
            <TableHead className="text-center w-8">A</TableHead>
            <TableHead className="text-center w-16">LH/DN</TableHead>
            <TableHead className="text-center w-20">GPM/XPM</TableHead>
            <TableHead className="text-right w-16">DMG</TableHead>
            <TableHead className="text-right w-16">BLD</TableHead>
            <TableHead className="text-right w-14">HEAL</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {players.map((player) => (
            <TableRow key={player.steam_id} className="text-sm">
              <TableCell className="p-1">
                <img
                  src={getHeroIcon(player.hero_id)}
                  alt={getHeroName(player.hero_id)}
                  className="w-9 h-9 rounded"
                  title={getHeroName(player.hero_id)}
                />
              </TableCell>
              <TableCell className="font-medium">
                {player.username ?? 'Unknown'}
              </TableCell>
              <TableCell className="text-center text-green-400">
                {player.kills}
              </TableCell>
              <TableCell className="text-center text-red-400">
                {player.deaths}
              </TableCell>
              <TableCell className="text-center text-muted-foreground">
                {player.assists}
              </TableCell>
              <TableCell className="text-center">
                {player.last_hits}
                <span className="text-muted-foreground">/</span>
                {player.denies}
              </TableCell>
              <TableCell className="text-center">
                <span className="text-yellow-400">{player.gold_per_min}</span>
                <span className="text-muted-foreground">/</span>
                <span className="text-blue-400">{player.xp_per_min}</span>
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.hero_damage)}
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.tower_damage)}
              </TableCell>
              <TableCell className="text-right">
                {formatNumber(player.hero_healing)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

### MatchStatsModal (`components/bracket/modals/MatchStatsModal.tsx`)

```typescript
import { Suspense } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Skeleton } from '~/components/ui/skeleton';
import { useMatchStats } from '~/hooks/useMatchStats';
import { splitPlayersByTeam, formatDuration, formatMatchDate } from '~/lib/dota/utils';
import { PlayerStatsTable } from './PlayerStatsTable';
import { cn } from '~/lib/utils';

interface MatchStatsModalProps {
  open: boolean;
  onClose: () => void;
  matchId: number | null;
}

export function MatchStatsModal({ open, onClose, matchId }: MatchStatsModalProps) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        <Suspense fallback={<MatchStatsSkeleton />}>
          {matchId && <MatchStatsContent matchId={matchId} />}
        </Suspense>
      </DialogContent>
    </Dialog>
  );
}

function MatchStatsContent({ matchId }: { matchId: number }) {
  const { data: match } = useMatchStats(matchId);
  const { radiant, dire } = splitPlayersByTeam(match.players);

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center justify-between">
          <span>Match {match.match_id}</span>
          <span className="text-sm font-normal text-muted-foreground">
            {formatDuration(match.duration)} • {formatMatchDate(match.start_time)}
          </span>
        </DialogTitle>
      </DialogHeader>

      {/* Result Banner */}
      <div
        className={cn(
          'text-center py-3 rounded-md font-semibold text-lg',
          match.radiant_win
            ? 'bg-green-900/40 text-green-300'
            : 'bg-red-900/40 text-red-300'
        )}
      >
        {match.radiant_win ? 'Radiant Victory' : 'Dire Victory'}
      </div>

      {/* Team Tables */}
      <div className="space-y-6">
        <PlayerStatsTable
          players={radiant}
          team="Radiant"
          isWinner={match.radiant_win}
        />
        <PlayerStatsTable
          players={dire}
          team="Dire"
          isWinner={!match.radiant_win}
        />
      </div>
    </>
  );
}

function MatchStatsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
```

### MatchNode Integration (`components/bracket/nodes/MatchNode.tsx`)

```typescript
import { useState } from 'react';
import { MatchStatsModal } from '../modals/MatchStatsModal';
import { HeroIconRow } from './HeroIconRow';
import { cn } from '~/lib/utils';
import type { BracketMatch } from '../../types';

export function MatchNode({ data }: { data: BracketMatch }) {
  const [modalOpen, setModalOpen] = useState(false);

  const hasStats = data.steamMatchId !== undefined;

  return (
    <>
      <div
        className={cn(
          'p-3 rounded-lg border bg-card',
          hasStats && 'cursor-pointer hover:border-primary'
        )}
        onClick={() => hasStats && setModalOpen(true)}
      >
        {/* Team names, scores */}
        <div className="text-sm font-medium">{data.radiantTeam?.name ?? 'TBD'}</div>
        <div className="text-sm font-medium">{data.direTeam?.name ?? 'TBD'}</div>

        {/* Hero icons */}
        {hasStats && data.radiantHeroes && (
          <div className="mt-2 space-y-1">
            <HeroIconRow heroIds={data.radiantHeroes} isWinner={data.winner === 'radiant'} />
            <HeroIconRow heroIds={data.direHeroes} isWinner={data.winner === 'dire'} />
          </div>
        )}
      </div>

      <MatchStatsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        matchId={data.steamMatchId ?? null}
      />
    </>
  );
}
```

---

## Implementation Order

1. **Install dependency**: `npm add dotaconstants`
2. **Backend**: Add `MatchDetailSerializer` and `MatchDetailView`
3. **Data layer**: Create `heroes.ts`, `schemas.ts`, `utils.ts`
4. **Hook**: Create `useMatchStats.ts`
5. **Components**: Create `HeroIconRow`, `PlayerStatsTable`, `MatchStatsModal`
6. **Integration**: Update `MatchNode` to show icons and trigger modal

---

## File Changes Summary

### New Files

```
frontend/app/
├── lib/dota/
│   ├── heroes.ts
│   ├── schemas.ts
│   └── utils.ts
├── hooks/
│   └── useMatchStats.ts
└── components/bracket/
    ├── nodes/
    │   └── HeroIconRow.tsx
    └── modals/
        ├── MatchStatsModal.tsx
        └── PlayerStatsTable.tsx
```

### Modified Files

```
frontend/package.json              # Add dotaconstants
frontend/app/components/bracket/
    └── nodes/MatchNode.tsx        # Add hero icons + modal
backend/steam/
    ├── serializers.py             # Add MatchDetailSerializer
    ├── views.py                   # Add MatchDetailView
    └── urls.py                    # Add match detail route
```
