# Match Stats Display Implementation Plan

**Status:** Completed

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display hero icons on bracket match nodes and Dotabuff-style stats tables in a modal when clicked.

**Architecture:** Frontend-first approach using `dotaconstants` npm package for hero metadata. Backend exposes match details via REST API. Modal uses Suspense for loading states.

**Tech Stack:** React, TypeScript, TanStack Query, Zod, Shadcn UI, Django REST Framework

---

## Task 1: Install dotaconstants Package

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install the package**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/match-stats-display/frontend
npm add dotaconstants
```

**Step 2: Verify installation**

Run:
```bash
npm ls dotaconstants
```

Expected: Shows dotaconstants version installed

**Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add dotaconstants package for hero metadata"
```

---

## Task 2: Create Hero Lookup Module

**Files:**
- Create: `frontend/app/lib/dota/heroes.ts`

**Step 1: Create the heroes module**

```typescript
// frontend/app/lib/dota/heroes.ts
import heroesData from 'dotaconstants/build/heroes.json';

export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  img: string;
  icon: string;
  primary_attr: 'str' | 'agi' | 'int' | 'all';
}

export const heroes: Record<string, DotaHero> = heroesData;

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

**Step 2: Verify TypeScript compiles**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/match-stats-display/frontend
npx tsc --noEmit app/lib/dota/heroes.ts 2>&1 || echo "Check for errors"
```

**Step 3: Commit**

```bash
git add app/lib/dota/heroes.ts
git commit -m "feat: add hero lookup module using dotaconstants"
```

---

## Task 3: Create Zod Schemas for Match Data

**Files:**
- Create: `frontend/app/lib/dota/schemas.ts`

**Step 1: Create the schemas**

```typescript
// frontend/app/lib/dota/schemas.ts
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

**Step 2: Commit**

```bash
git add app/lib/dota/schemas.ts
git commit -m "feat: add Zod schemas for match data validation"
```

---

## Task 4: Create Utility Functions

**Files:**
- Create: `frontend/app/lib/dota/utils.ts`

**Step 1: Create utilities**

```typescript
// frontend/app/lib/dota/utils.ts
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

**Step 2: Create index file for clean imports**

```typescript
// frontend/app/lib/dota/index.ts
export * from './heroes';
export * from './schemas';
export * from './utils';
```

**Step 3: Commit**

```bash
git add app/lib/dota/utils.ts app/lib/dota/index.ts
git commit -m "feat: add dota utility functions and barrel export"
```

---

## Task 5: Backend - Add Match Detail Serializer

**Files:**
- Modify: `backend/steam/serializers.py`
- Test: `backend/steam/tests/test_serializers.py`

**Step 1: Write failing test**

Add to `backend/steam/tests/test_serializers.py`:

```python
from steam.serializers import MatchDetailSerializer, PlayerMatchStatsSerializer


class PlayerMatchStatsSerializerTest(TestCase):
    def test_serializes_player_with_username(self):
        user = CustomUser.objects.create(username="TestPlayer", visiblename="TestPlayer")
        match = Match.objects.create(
            match_id=12345,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        stats = PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=user,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=500,
        )
        serializer = PlayerMatchStatsSerializer(stats)
        data = serializer.data
        self.assertEqual(data['username'], 'TestPlayer')
        self.assertEqual(data['hero_id'], 1)
        self.assertEqual(data['kills'], 10)


class MatchDetailSerializerTest(TestCase):
    def test_serializes_match_with_players(self):
        match = Match.objects.create(
            match_id=12345,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=500,
        )
        serializer = MatchDetailSerializer(match)
        data = serializer.data
        self.assertEqual(data['match_id'], 12345)
        self.assertTrue(data['radiant_win'])
        self.assertEqual(len(data['players']), 1)
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/match-stats-display/backend
source ../.venv/bin/activate
DISABLE_CACHE=true python manage.py test steam.tests.test_serializers -v 2
```

Expected: ImportError or AttributeError (serializers don't exist yet)

**Step 3: Add the serializers**

Add to `backend/steam/serializers.py`:

```python
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

**Step 4: Run tests to verify they pass**

Run:
```bash
DISABLE_CACHE=true python manage.py test steam.tests.test_serializers -v 2
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/steam/serializers.py backend/steam/tests/test_serializers.py
git commit -m "feat: add MatchDetailSerializer with player stats"
```

---

## Task 6: Backend - Add Match Detail API Endpoint

**Files:**
- Modify: `backend/steam/views.py`
- Modify: `backend/steam/urls.py`
- Test: `backend/steam/tests/test_api.py`

**Step 1: Write failing test**

Add to `backend/steam/tests/test_api.py`:

```python
class MatchDetailViewTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=99999,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=5,
            deaths=3,
            assists=10,
            gold_per_min=500,
            xp_per_min=600,
            last_hits=150,
            denies=5,
            hero_damage=20000,
            tower_damage=2000,
            hero_healing=0,
        )

    def test_get_match_detail(self):
        response = self.client.get('/api/steam/matches/99999/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['match_id'], 99999)
        self.assertEqual(len(data['players']), 1)
        self.assertEqual(data['players'][0]['hero_id'], 1)

    def test_get_match_not_found(self):
        response = self.client.get('/api/steam/matches/1/')
        self.assertEqual(response.status_code, 404)
```

**Step 2: Run test to verify it fails**

Run:
```bash
DISABLE_CACHE=true python manage.py test steam.tests.test_api.MatchDetailViewTest -v 2
```

Expected: 404 (URL not configured)

**Step 3: Add the view**

Add to `backend/steam/views.py`:

```python
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from .serializers import MatchDetailSerializer


class MatchDetailView(RetrieveAPIView):
    queryset = Match.objects.prefetch_related('players__user')
    serializer_class = MatchDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'match_id'
```

**Step 4: Add the URL**

Add to `backend/steam/urls.py`:

```python
from .views import MatchDetailView

# Add to urlpatterns:
path('matches/<int:match_id>/', MatchDetailView.as_view(), name='match-detail'),
```

**Step 5: Run tests to verify they pass**

Run:
```bash
DISABLE_CACHE=true python manage.py test steam.tests.test_api.MatchDetailViewTest -v 2
```

Expected: PASS

**Step 6: Commit**

```bash
git add backend/steam/views.py backend/steam/urls.py backend/steam/tests/test_api.py
git commit -m "feat: add match detail API endpoint"
```

---

## Task 7: Frontend - Create useMatchStats Hook

**Files:**
- Create: `frontend/app/hooks/useMatchStats.ts`

**Step 1: Create the hook**

```typescript
// frontend/app/hooks/useMatchStats.ts
import { useQuery } from '@tanstack/react-query';
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
  return useQuery({
    queryKey: ['match', matchId],
    queryFn: () => fetchMatch(matchId!),
    enabled: matchId !== null,
  });
}
```

**Step 2: Commit**

```bash
git add app/hooks/useMatchStats.ts
git commit -m "feat: add useMatchStats hook for fetching match data"
```

---

## Task 8: Frontend - Create HeroIconRow Component

**Files:**
- Create: `frontend/app/components/bracket/nodes/HeroIconRow.tsx`

**Step 1: Create the component**

```typescript
// frontend/app/components/bracket/nodes/HeroIconRow.tsx
import { getHeroIcon, getHeroName } from '~/lib/dota';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

interface HeroIconRowProps {
  heroIds: number[];
  isWinner?: boolean;
}

export function HeroIconRow({ heroIds, isWinner }: HeroIconRowProps) {
  return (
    <div
      className={cn('flex gap-0.5', isWinner && 'ring-1 ring-green-500 rounded')}
    >
      {heroIds.map((heroId, index) => (
        <Tooltip key={`${heroId}-${index}`}>
          <TooltipTrigger asChild>
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

**Step 2: Commit**

```bash
git add app/components/bracket/nodes/HeroIconRow.tsx
git commit -m "feat: add HeroIconRow component for compact hero display"
```

---

## Task 9: Frontend - Create PlayerStatsTable Component

**Files:**
- Create: `frontend/app/components/bracket/modals/PlayerStatsTable.tsx`

**Step 1: Create the component**

```typescript
// frontend/app/components/bracket/modals/PlayerStatsTable.tsx
import { getHeroIcon, getHeroName } from '~/lib/dota';
import { formatNumber } from '~/lib/dota/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { cn } from '~/lib/utils';
import type { PlayerMatchStats } from '~/lib/dota/schemas';

interface PlayerStatsTableProps {
  players: PlayerMatchStats[];
  team: 'Radiant' | 'Dire';
  isWinner: boolean;
}

export function PlayerStatsTable({
  players,
  team,
  isWinner,
}: PlayerStatsTableProps) {
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
      <div
        className={cn(
          'flex items-center justify-between px-3 py-2 rounded',
          isWinner ? 'bg-green-900/30' : 'bg-red-900/30'
        )}
      >
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'font-semibold uppercase',
              team === 'Radiant' ? 'text-green-400' : 'text-red-400'
            )}
          >
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

**Step 2: Commit**

```bash
git add app/components/bracket/modals/PlayerStatsTable.tsx
git commit -m "feat: add PlayerStatsTable component with Dotabuff-style layout"
```

---

## Task 10: Frontend - Create MatchStatsModal Component

**Files:**
- Create: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**Step 1: Create the component**

```typescript
// frontend/app/components/bracket/modals/MatchStatsModal.tsx
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Skeleton } from '~/components/ui/skeleton';
import { useMatchStats } from '~/hooks/useMatchStats';
import {
  splitPlayersByTeam,
  formatDuration,
  formatMatchDate,
} from '~/lib/dota/utils';
import { PlayerStatsTable } from './PlayerStatsTable';
import { cn } from '~/lib/utils';

interface MatchStatsModalProps {
  open: boolean;
  onClose: () => void;
  matchId: number | null;
}

export function MatchStatsModal({
  open,
  onClose,
  matchId,
}: MatchStatsModalProps) {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        {matchId ? (
          <MatchStatsContent matchId={matchId} />
        ) : (
          <MatchStatsSkeleton />
        )}
      </DialogContent>
    </Dialog>
  );
}

function MatchStatsContent({ matchId }: { matchId: number }) {
  const { data: match, isLoading, error } = useMatchStats(matchId);

  if (isLoading) {
    return <MatchStatsSkeleton />;
  }

  if (error || !match) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Failed to load match data
      </div>
    );
  }

  const { radiant, dire } = splitPlayersByTeam(match.players);

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center justify-between">
          <span>Match {match.match_id}</span>
          <span className="text-sm font-normal text-muted-foreground">
            {formatDuration(match.duration)} •{' '}
            {formatMatchDate(match.start_time)}
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

**Step 2: Create barrel export**

```typescript
// frontend/app/components/bracket/modals/index.ts
export { MatchStatsModal } from './MatchStatsModal';
export { PlayerStatsTable } from './PlayerStatsTable';
```

**Step 3: Commit**

```bash
git add app/components/bracket/modals/MatchStatsModal.tsx app/components/bracket/modals/index.ts
git commit -m "feat: add MatchStatsModal with loading and error states"
```

---

## Task 11: Create Bracket Nodes Index

**Files:**
- Create: `frontend/app/components/bracket/nodes/index.ts`

**Step 1: Create barrel export**

```typescript
// frontend/app/components/bracket/nodes/index.ts
export { HeroIconRow } from './HeroIconRow';
```

**Step 2: Commit**

```bash
git add app/components/bracket/nodes/index.ts
git commit -m "chore: add barrel export for bracket nodes"
```

---

## Task 12: Run Full Test Suite

**Step 1: Run backend tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/match-stats-display/backend
source ../.venv/bin/activate
DISABLE_CACHE=true python manage.py test steam -v 1
```

Expected: All tests pass

**Step 2: Run frontend build check**

```bash
cd /home/kettle/git_repos/website/.worktrees/match-stats-display/frontend
npm run build 2>&1 | tail -20
```

Expected: Build succeeds (or only pre-existing errors)

**Step 3: Final commit if any fixes needed**

```bash
git status
# If clean, no action needed
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Install dotaconstants | package.json |
| 2 | Hero lookup module | lib/dota/heroes.ts |
| 3 | Zod schemas | lib/dota/schemas.ts |
| 4 | Utility functions | lib/dota/utils.ts, index.ts |
| 5 | Backend serializers | steam/serializers.py |
| 6 | Backend API endpoint | steam/views.py, urls.py |
| 7 | useMatchStats hook | hooks/useMatchStats.ts |
| 8 | HeroIconRow component | bracket/nodes/HeroIconRow.tsx |
| 9 | PlayerStatsTable component | bracket/modals/PlayerStatsTable.tsx |
| 10 | MatchStatsModal component | bracket/modals/MatchStatsModal.tsx |
| 11 | Barrel exports | bracket/nodes/index.ts |
| 12 | Full test suite | - |
