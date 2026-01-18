# League Page Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add tabbed navigation to League page with Info, Tournaments, and Matches tabs, plus an Edit League modal for admins.

**Architecture:** Frontend uses shadcn Tabs component with URL-based tab routing. Backend adds a `/leagues/{pk}/matches/` endpoint returning games from league tournaments. LeagueMatchCard displays captain avatars/names. Edit modal uses Zod + React Hook Form pattern.

**Tech Stack:** React, TypeScript, Zod, React Hook Form, shadcn/ui (Tabs, Dialog), Django REST Framework

**Review Notes:** This plan was reviewed by 4 agents and corrected for:
- IsLeagueAdmin already exists in `permissions_org.py`
- Game model has no `steam_match` FK - uses `gameid` field
- Route uses `leagueId` not `pk`, path is `leagues/` not `league/`
- DotaMatchStatsModal uses `onClose` + `matchId` props
- Use axios instead of fetch for API calls
- UserAvatar doesn't exist - use Avatar + AvatarUrl pattern

---

## Task 0: Backend - Update Game Model

**Files:**
- Modify: `backend/app/models.py`

**Context:** Game currently has a required `tournament` FK. User requested:
1. Add `league` FK to Game (optional, ForeignKey to League)
2. Make `tournament` FK optional (null=True, blank=True)
3. Keep `gameid` for steam match linking (already exists as IntegerField)

**Step 1: Update Game model fields**

Find the `Game` model and update the tournament FK to be optional, then add a league FK:

```python
class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="games", on_delete=models.CASCADE,
        null=True, blank=True  # Now optional
    )
    league = models.ForeignKey(
        "League", related_name="games", on_delete=models.CASCADE,
        null=True, blank=True  # Games can belong directly to a league
    )
    # ... rest of model unchanged
```

**Step 2: Update __str__ method**

The `__str__` method references `self.tournament.name` which will fail if tournament is None:

```python
def __str__(self):
    tourn_name = self.tournament.name if self.tournament else "No Tournament"
    radiant = self.radiant_team.name if self.radiant_team else "TBD"
    dire = self.dire_team.name if self.dire_team else "TBD"
    return f"{radiant} vs {dire} in {tourn_name}"
```

**Step 3: Update save method cache invalidation**

The save method invalidates tournament cache - update to handle None:

```python
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    from cacheops import invalidate_model, invalidate_obj

    if self.tournament_id:
        invalidate_obj(self.tournament)
    if self.league_id:
        invalidate_obj(self.league)
    invalidate_model(Team)
```

**Step 4: Create and run migration**

```bash
cd backend
python manage.py makemigrations app -n game_add_league_optional_tournament
python manage.py migrate
```

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add league FK to Game, make tournament optional"
```

---

## Task 1: Backend - Add League Matches Endpoint

**Files:**
- Modify: `backend/app/views_main.py`
- Modify: `backend/app/serializers.py`

**Context:** `IsLeagueAdmin` permission already exists in `backend/app/permissions_org.py` and is used by LeagueView.

**Step 1: Create LeagueMatchSerializer**

Add to `backend/app/serializers.py`:

```python
class LeagueMatchSerializer(serializers.ModelSerializer):
    """Serializer for matches in a league context with captain info."""
    radiant_captain = TournamentUserSerializer(source='radiant_team.captain', read_only=True)
    dire_captain = TournamentUserSerializer(source='dire_team.captain', read_only=True)
    radiant_team_name = serializers.CharField(source='radiant_team.name', read_only=True)
    dire_team_name = serializers.CharField(source='dire_team.name', read_only=True)
    tournament_name = serializers.CharField(source='tournament.name', read_only=True)
    tournament_pk = serializers.IntegerField(source='tournament.pk', read_only=True)
    date_played = serializers.DateField(source='tournament.date_played', read_only=True)

    class Meta:
        model = Game
        fields = [
            'pk', 'tournament_pk', 'tournament_name', 'round', 'date_played',
            'radiant_team', 'dire_team', 'radiant_team_name', 'dire_team_name',
            'radiant_captain', 'dire_captain', 'winning_team', 'gameid',
        ]
```

**Step 2: Add matches action to LeagueView**

Add import at top of `backend/app/views_main.py`:
```python
from rest_framework.decorators import action
```

Add to `LeagueView` class:

```python
from django.db.models import Q

@action(detail=True, methods=['get'])
def matches(self, request, pk=None):
    """Get all matches for this league (direct or via tournaments)."""
    league = self.get_object()
    # Games directly belonging to league OR games in tournaments belonging to league
    games = Game.objects.filter(
        Q(league=league) | Q(tournament__league=league)
    ).select_related(
        'tournament',
        'league',
        'radiant_team__captain',
        'dire_team__captain',
        'winning_team',
    ).order_by('-pk')

    # Optional filtering
    tournament_pk = request.query_params.get('tournament')
    if tournament_pk:
        games = games.filter(tournament_id=tournament_pk)

    linked_only = request.query_params.get('linked_only')
    if linked_only == 'true':
        games = games.filter(gameid__isnull=False)

    serializer = LeagueMatchSerializer(games, many=True)
    return Response(serializer.data)
```

**Step 3: Commit**

```bash
git add backend/app/views_main.py backend/app/serializers.py
git commit -m "feat: add /leagues/{pk}/matches/ endpoint"
```

---

## Task 2: Frontend - Add API Function for League Matches

**Files:**
- Modify: `frontend/app/components/api/api.tsx`

**Step 1: Add getLeagueMatches function using axios pattern**

```typescript
export async function getLeagueMatches(
  leaguePk: number,
  options?: { tournament?: number; linkedOnly?: boolean }
): Promise<LeagueMatchType[]> {
  const params = new URLSearchParams();
  if (options?.tournament) params.append('tournament', options.tournament.toString());
  if (options?.linkedOnly) params.append('linked_only', 'true');

  const queryString = params.toString() ? `?${params.toString()}` : '';
  const response = await axios.get<LeagueMatchType[]>(
    `/leagues/${leaguePk}/matches/${queryString}`
  );
  return response.data;
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/api/api.tsx
git commit -m "feat: add getLeagueMatches API function"
```

---

## Task 3: Frontend - Add LeagueMatch Schema and Types

**Files:**
- Modify: `frontend/app/components/league/schemas.ts`

**Step 1: Add LeagueMatchSchema (without steam_match - use gameid for linking)**

```typescript
import { z } from 'zod';
import { UserSchema } from '../user';

// LeagueMatch schema - uses gameid to link to Steam matches
export const LeagueMatchSchema = z.object({
  pk: z.number(),
  tournament_pk: z.number(),
  tournament_name: z.string().nullable(),
  round: z.number().nullable(),
  date_played: z.string().nullable(),
  radiant_team: z.number().nullable(),
  dire_team: z.number().nullable(),
  radiant_team_name: z.string().nullable(),
  dire_team_name: z.string().nullable(),
  radiant_captain: UserSchema.nullable(),
  dire_captain: UserSchema.nullable(),
  winning_team: z.number().nullable(),
  gameid: z.number().nullable(),  // Steam match_id for linking
});

export type LeagueMatchType = z.infer<typeof LeagueMatchSchema>;

// Edit league schema
export const EditLeagueSchema = z.object({
  name: z.string().min(1, 'League name is required').max(255),
  description: z.string().max(10000).optional().default(''),
  rules: z.string().max(50000).optional().default(''),
  prize_pool: z.string().max(100).optional().default(''),
});

export type EditLeagueInput = z.infer<typeof EditLeagueSchema>;
```

**Step 2: Export from index**

Update `frontend/app/components/league/index.ts` to export new types.

**Step 3: Commit**

```bash
git add frontend/app/components/league/schemas.ts frontend/app/components/league/index.ts
git commit -m "feat: add LeagueMatchSchema and EditLeagueSchema"
```

---

## Task 4: Frontend - Create useLeagueMatches Hook

**Files:**
- Create: `frontend/app/components/league/hooks/useLeagueMatches.ts`

**Step 1: Create the hook**

```typescript
import { useCallback, useEffect, useState } from 'react';
import { getLeagueMatches } from '~/components/api/api';
import type { LeagueMatchType } from '../schemas';

interface UseLeagueMatchesOptions {
  tournament?: number;
  linkedOnly?: boolean;
}

export function useLeagueMatches(leaguePk: number | null, options?: UseLeagueMatchesOptions) {
  const [matches, setMatches] = useState<LeagueMatchType[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchMatches = useCallback(async () => {
    if (!leaguePk) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getLeagueMatches(leaguePk, options);
      setMatches(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch matches'));
    } finally {
      setIsLoading(false);
    }
  }, [leaguePk, options?.tournament, options?.linkedOnly]);

  useEffect(() => {
    fetchMatches();
  }, [fetchMatches]);

  return { matches, isLoading, error, refetch: fetchMatches };
}
```

**Step 2: Create hooks index file**

Create `frontend/app/components/league/hooks/index.ts`:

```typescript
export * from './useLeague';
export * from './useLeagues';
export * from './useLeagueMatches';
```

**Step 3: Commit**

```bash
git add frontend/app/components/league/hooks/
git commit -m "feat: add useLeagueMatches hook"
```

---

## Task 5: Frontend - Create LeagueMatchCard Component

**Files:**
- Create: `frontend/app/components/league/LeagueMatchCard.tsx`

**Step 1: Create the component (using Avatar + AvatarUrl pattern, correct DotaMatchStatsModal props)**

```typescript
import { format } from 'date-fns';
import { Calendar, Trophy, Link as LinkIcon } from 'lucide-react';
import { useState } from 'react';

import { Card, CardContent } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { Avatar, AvatarImage, AvatarFallback } from '~/components/ui/avatar';
import { AvatarUrl } from '~/components/user/avatar';
import { PlayerPopover } from '~/components/player/PlayerPopover';
import { DotaMatchStatsModal } from '~/components/bracket/modals/DotaMatchStatsModal';
import { cn } from '~/lib/utils';
import type { LeagueMatchType } from './schemas';
import type { UserType } from '~/components/user/types';

interface Props {
  match: LeagueMatchType;
}

// Helper component for captain avatar
const CaptainAvatar: React.FC<{ user: UserType; size?: 'sm' | 'md' }> = ({ user, size = 'md' }) => {
  const sizeClass = size === 'sm' ? 'h-6 w-6' : 'h-10 w-10';
  return (
    <Avatar className={sizeClass}>
      <AvatarImage src={AvatarUrl(user)} alt={user.nickname || user.username} />
      <AvatarFallback>{(user.nickname || user.username).charAt(0).toUpperCase()}</AvatarFallback>
    </Avatar>
  );
};

export const LeagueMatchCard: React.FC<Props> = ({ match }) => {
  const [showStats, setShowStats] = useState(false);

  const radiantWon = match.winning_team === match.radiant_team;
  const direWon = match.winning_team === match.dire_team;
  const hasResult = match.winning_team !== null;
  const hasSteamLink = !!match.gameid;

  return (
    <>
      <Card className="hover:shadow-md transition-shadow">
        <CardContent className="p-4">
          {/* Header: Tournament + Round */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {match.tournament_name}
              </span>
              {match.round && (
                <Badge variant="outline" className="text-xs">
                  Round {match.round}
                </Badge>
              )}
            </div>
            {hasSteamLink && (
              <Badge variant="secondary" className="text-xs">
                <LinkIcon className="h-3 w-3 mr-1" />
                Steam Linked
              </Badge>
            )}
          </div>

          {/* Captains Display */}
          <div className="flex items-center justify-between gap-4">
            {/* Radiant Captain */}
            <div className={cn(
              "flex items-center gap-3 flex-1",
              radiantWon && "ring-2 ring-green-500 rounded-lg p-2"
            )}>
              {match.radiant_captain ? (
                <PlayerPopover player={match.radiant_captain}>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <CaptainAvatar user={match.radiant_captain} />
                    <div>
                      <p className="font-medium text-green-600">
                        {match.radiant_captain.nickname || match.radiant_captain.username}
                      </p>
                      <p className="text-xs text-muted-foreground">Radiant</p>
                    </div>
                  </div>
                </PlayerPopover>
              ) : (
                <div className="text-muted-foreground">TBD</div>
              )}
            </div>

            {/* VS / Score */}
            <div className="text-center px-4">
              {hasResult ? (
                <div className="text-lg font-bold">
                  <span className={radiantWon ? 'text-green-600' : 'text-muted-foreground'}>
                    {radiantWon ? 'W' : 'L'}
                  </span>
                  <span className="mx-2">-</span>
                  <span className={direWon ? 'text-red-600' : 'text-muted-foreground'}>
                    {direWon ? 'W' : 'L'}
                  </span>
                </div>
              ) : (
                <span className="text-muted-foreground font-medium">vs</span>
              )}
            </div>

            {/* Dire Captain */}
            <div className={cn(
              "flex items-center gap-3 flex-1 justify-end",
              direWon && "ring-2 ring-red-500 rounded-lg p-2"
            )}>
              {match.dire_captain ? (
                <PlayerPopover player={match.dire_captain}>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <div className="text-right">
                      <p className="font-medium text-red-600">
                        {match.dire_captain.nickname || match.dire_captain.username}
                      </p>
                      <p className="text-xs text-muted-foreground">Dire</p>
                    </div>
                    <CaptainAvatar user={match.dire_captain} />
                  </div>
                </PlayerPopover>
              ) : (
                <div className="text-muted-foreground">TBD</div>
              )}
            </div>
          </div>

          {/* Footer: Date + Actions */}
          <div className="flex items-center justify-between mt-4 pt-3 border-t">
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              {match.date_played && (
                <div className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  {format(new Date(match.date_played), 'MMM d, yyyy')}
                </div>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowStats(true)}
              disabled={!hasSteamLink}
            >
              View Details
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Stats Modal - uses onClose and matchId props */}
      {hasSteamLink && (
        <DotaMatchStatsModal
          open={showStats}
          onClose={() => setShowStats(false)}
          matchId={match.gameid}
        />
      )}
    </>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/LeagueMatchCard.tsx
git commit -m "feat: create LeagueMatchCard component with captain display"
```

---

## Task 6: Frontend - Create InfoTab Component

**Files:**
- Create: `frontend/app/components/league/tabs/InfoTab.tsx`

**Step 1: Create the component (plain text, no react-markdown)**

```typescript
import { Award, Users, FileText } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Avatar, AvatarImage, AvatarFallback } from '~/components/ui/avatar';
import { AvatarUrl } from '~/components/user/avatar';
import type { LeagueType } from '../schemas';

interface Props {
  league: LeagueType;
}

export const InfoTab: React.FC<Props> = ({ league }) => {
  return (
    <div className="space-y-6">
      {/* Prize Pool */}
      {league.prize_pool && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Award className="h-5 w-5" />
              Prize Pool
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{league.prize_pool}</p>
          </CardContent>
        </Card>
      )}

      {/* Description */}
      {league.description && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              About
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
            {league.description}
          </CardContent>
        </Card>
      )}

      {/* Rules */}
      {league.rules && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Rules
            </CardTitle>
          </CardHeader>
          <CardContent className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
            {league.rules}
          </CardContent>
        </Card>
      )}

      {/* Admins */}
      {league.admins && league.admins.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              League Admins
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {league.admins.map((admin) => (
                <div key={admin.pk} className="flex items-center gap-2">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={AvatarUrl(admin)} alt={admin.nickname || admin.username} />
                    <AvatarFallback>{(admin.nickname || admin.username).charAt(0).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <span className="text-sm">{admin.nickname || admin.username}</span>
                  <Badge variant="secondary" className="text-xs">Admin</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/tabs/InfoTab.tsx
git commit -m "feat: create InfoTab component for league details"
```

---

## Task 7: Frontend - Create TournamentsTab Component

**Files:**
- Create: `frontend/app/components/league/tabs/TournamentsTab.tsx`

**Step 1: Create the component**

```typescript
import { Trophy } from 'lucide-react';
import { useState } from 'react';

import { TournamentCard } from '~/components/tournament/card/TournamentCard';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import type { LeagueType } from '../schemas';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
}

export const TournamentsTab: React.FC<Props> = ({ league, tournaments }) => {
  const [stateFilter, setStateFilter] = useState<string>('all');

  const filteredTournaments = tournaments.filter((t) => {
    if (stateFilter === 'all') return true;
    return t.state === stateFilter;
  });

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium flex items-center gap-2">
          <Trophy className="h-5 w-5" />
          Tournaments ({filteredTournaments.length})
        </h3>
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Filter by state" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All States</SelectItem>
            <SelectItem value="future">Future</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="past">Past</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Tournament Grid */}
      {filteredTournaments.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTournaments.map((tournament) => (
            <TournamentCard key={tournament.pk} tournament={tournament} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          No tournaments found for this league.
        </div>
      )}
    </div>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/tabs/TournamentsTab.tsx
git commit -m "feat: create TournamentsTab component"
```

---

## Task 8: Frontend - Create MatchesTab Component

**Files:**
- Create: `frontend/app/components/league/tabs/MatchesTab.tsx`

**Step 1: Create the component (using Button toggle instead of Checkbox)**

```typescript
import { Gamepad2, Loader2, Check } from 'lucide-react';
import { useState } from 'react';

import { LeagueMatchCard } from '../LeagueMatchCard';
import { useLeagueMatches } from '../hooks/useLeagueMatches';
import { Button } from '~/components/ui/button';

interface Props {
  leaguePk: number;
}

export const MatchesTab: React.FC<Props> = ({ leaguePk }) => {
  const [linkedOnly, setLinkedOnly] = useState(false);
  const { matches, isLoading, error } = useLeagueMatches(leaguePk, { linkedOnly });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Failed to load matches: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium flex items-center gap-2">
          <Gamepad2 className="h-5 w-5" />
          Matches ({matches.length})
        </h3>
        <Button
          variant={linkedOnly ? 'default' : 'outline'}
          size="sm"
          onClick={() => setLinkedOnly(!linkedOnly)}
        >
          {linkedOnly && <Check className="h-4 w-4 mr-1" />}
          Steam linked only
        </Button>
      </div>

      {/* Match List */}
      {matches.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {matches.map((match) => (
            <LeagueMatchCard key={match.pk} match={match} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          No matches found for this league.
        </div>
      )}
    </div>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/tabs/MatchesTab.tsx
git commit -m "feat: create MatchesTab component with Steam filter"
```

---

## Task 9: Frontend - Create EditLeagueModal Component

**Files:**
- Create: `frontend/app/components/league/EditLeagueModal.tsx`

**Step 1: Create the component (with form reset on open)**

```typescript
import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { updateLeague } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { DIALOG_CSS } from '~/components/reusable/modal';
import { EditLeagueSchema, type EditLeagueInput, type LeagueType } from './schemas';

interface EditLeagueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  league: LeagueType;
  onSuccess?: () => void;
}

export function EditLeagueModal({
  open,
  onOpenChange,
  league,
  onSuccess,
}: EditLeagueModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<EditLeagueInput>({
    resolver: zodResolver(EditLeagueSchema),
    defaultValues: {
      name: league.name || '',
      description: league.description || '',
      rules: league.rules || '',
      prize_pool: league.prize_pool || '',
    },
  });

  // Reset form when league changes or modal opens
  useEffect(() => {
    if (open) {
      form.reset({
        name: league.name || '',
        description: league.description || '',
        rules: league.rules || '',
        prize_pool: league.prize_pool || '',
      });
    }
  }, [open, league, form]);

  async function onSubmit(data: EditLeagueInput) {
    if (isSubmitting || !league.pk) return;
    setIsSubmitting(true);

    try {
      await updateLeague(league.pk, data);
      toast.success('League updated successfully');
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update league';
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={DIALOG_CSS} data-testid="edit-league-modal">
        <DialogHeader>
          <DialogTitle>Edit League</DialogTitle>
          <DialogDescription>
            Update league information.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>League Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter league name"
                      data-testid="league-name-input"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="prize_pool"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Prize Pool</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g., $1,000"
                      data-testid="league-prize-input"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="League description..."
                      rows={4}
                      data-testid="league-description-input"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="rules"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Rules</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="League rules..."
                      rows={6}
                      data-testid="league-rules-input"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting}
                data-testid="league-submit-button"
              >
                {isSubmitting ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/EditLeagueModal.tsx
git commit -m "feat: create EditLeagueModal with Zod validation"
```

---

## Task 10: Frontend - Create LeagueTabs Component

**Files:**
- Create: `frontend/app/components/league/LeagueTabs.tsx`

**Step 1: Create the component**

```typescript
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { InfoTab } from './tabs/InfoTab';
import { TournamentsTab } from './tabs/TournamentsTab';
import { MatchesTab } from './tabs/MatchesTab';
import type { LeagueType } from './schemas';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export const LeagueTabs: React.FC<Props> = ({
  league,
  tournaments,
  activeTab,
  onTabChange,
}) => {
  return (
    <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
      <TabsList className="grid w-full grid-cols-3">
        <TabsTrigger value="info" data-testid="league-tab-info">
          Info
        </TabsTrigger>
        <TabsTrigger value="tournaments" data-testid="league-tab-tournaments">
          Tournaments ({tournaments.length})
        </TabsTrigger>
        <TabsTrigger value="matches" data-testid="league-tab-matches">
          Matches
        </TabsTrigger>
      </TabsList>

      <TabsContent value="info" className="mt-6">
        <InfoTab league={league} />
      </TabsContent>

      <TabsContent value="tournaments" className="mt-6">
        <TournamentsTab league={league} tournaments={tournaments} />
      </TabsContent>

      <TabsContent value="matches" className="mt-6">
        {league.pk && <MatchesTab leaguePk={league.pk} />}
      </TabsContent>
    </Tabs>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/league/LeagueTabs.tsx
git commit -m "feat: create LeagueTabs component"
```

---

## Task 11: Frontend - Create tabs directory index and update exports

**Files:**
- Create: `frontend/app/components/league/tabs/index.ts`
- Modify: `frontend/app/components/league/index.ts`

**Step 1: Create tabs index file**

```typescript
export * from './InfoTab';
export * from './TournamentsTab';
export * from './MatchesTab';
```

**Step 2: Update main league index**

```typescript
export * from './schemas';
export * from './hooks/useLeague';
export * from './hooks/useLeagues';
export * from './hooks/useLeagueMatches';
export * from './LeagueCard';
export * from './LeagueMatchCard';
export * from './LeagueTabs';
export { EditLeagueModal } from './EditLeagueModal';
```

**Step 3: Commit**

```bash
git add frontend/app/components/league/tabs/index.ts frontend/app/components/league/index.ts
git commit -m "feat: add league tabs index exports"
```

---

## Task 12: Frontend - Update League Route

**Files:**
- Modify: `frontend/app/routes/league.tsx`
- Modify: `frontend/app/routes.tsx`

**Step 1: Update the route component (uses leagueId, not pk)**

```typescript
import { useParams, useNavigate } from 'react-router';
import { useState, useEffect } from 'react';
import { Trophy, Building2, Loader2, Pencil } from 'lucide-react';

import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { useLeague, LeagueTabs, EditLeagueModal } from '~/components/league';
import { useUserStore } from '~/store/userStore';

export default function LeaguePage() {
  const { leagueId, tab } = useParams<{ leagueId: string; tab?: string }>();
  const navigate = useNavigate();
  const pk = leagueId ? parseInt(leagueId, 10) : undefined;

  const { league, isLoading, error, refetch } = useLeague(pk);
  const currentUser = useUserStore((state) => state.currentUser);
  const tournaments = useUserStore((state) => state.tournaments);
  const getTournaments = useUserStore((state) => state.getTournaments);

  const [activeTab, setActiveTab] = useState(tab || 'info');
  const [editModalOpen, setEditModalOpen] = useState(false);

  // Fetch tournaments
  useEffect(() => {
    getTournaments();
  }, [getTournaments]);

  // Sync tab with URL
  useEffect(() => {
    if (tab && tab !== activeTab) {
      setActiveTab(tab);
    }
  }, [tab, activeTab]);

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    navigate(`/leagues/${leagueId}/${newTab}`, { replace: true });
  };

  // Filter tournaments for this league
  const leagueTournaments = tournaments?.filter(
    (t) => t.league === pk
  ) || [];

  // Permission check for edit
  const canEdit = currentUser?.is_staff ||
    currentUser?.is_superuser ||
    (league?.admin_ids && currentUser?.pk && league.admin_ids.includes(currentUser.pk));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !league) {
    return (
      <div className="text-center py-12 text-destructive">
        {error?.message || 'League not found'}
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <Trophy className="h-8 w-8 text-primary" />
            <h1 className="text-3xl font-bold">{league.name}</h1>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            {league.organization_name && (
              <Badge variant="outline" className="flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {league.organization_name}
              </Badge>
            )}
            {league.steam_league_id && (
              <Badge variant="secondary">
                Steam ID: {league.steam_league_id}
              </Badge>
            )}
          </div>
        </div>

        {canEdit && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditModalOpen(true)}
            data-testid="edit-league-button"
          >
            <Pencil className="h-4 w-4 mr-2" />
            Edit League
          </Button>
        )}
      </div>

      {/* Tabs */}
      <LeagueTabs
        league={league}
        tournaments={leagueTournaments}
        activeTab={activeTab}
        onTabChange={handleTabChange}
      />

      {/* Edit Modal */}
      {canEdit && league && (
        <EditLeagueModal
          open={editModalOpen}
          onOpenChange={setEditModalOpen}
          league={league}
          onSuccess={refetch}
        />
      )}
    </div>
  );
}
```

**Step 2: Update routes.tsx to add tab parameter**

Find the league route and update it:

```typescript
route('leagues/:leagueId/:tab?', 'routes/league.tsx'),
```

**Step 3: Commit**

```bash
git add frontend/app/routes/league.tsx frontend/app/routes.tsx
git commit -m "feat: update League route with tabs and edit modal"
```

---

## Task 13: Verify and Test

**Step 1: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

**Step 2: Start dev environment**

```bash
inv dev.test
```

**Step 3: Manual test checklist**

- [ ] Navigate to `/leagues/1/info` - Info tab displays
- [ ] Navigate to `/leagues/1/tournaments` - Tournaments tab displays
- [ ] Navigate to `/leagues/1/matches` - Matches tab displays with cards
- [ ] Click LeagueMatchCard "View Details" - Modal opens with Steam stats
- [ ] As admin, click "Edit League" - Modal opens
- [ ] Submit edit form - League updates successfully
- [ ] Tab navigation updates URL correctly

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete League page tabs implementation"
```

---

## Summary

| Task | Component | Description |
|------|-----------|-------------|
| 0 | Game model | Add league FK, make tournament optional |
| 1 | LeagueView.matches | Add matches endpoint to backend |
| 2 | api.tsx | Add getLeagueMatches function |
| 3 | schemas.ts | Add LeagueMatch and EditLeague schemas |
| 4 | useLeagueMatches | Create hook for fetching matches |
| 5 | LeagueMatchCard | Card component with captain display |
| 6 | InfoTab | League info, rules, admins |
| 7 | TournamentsTab | Tournament list with filter |
| 8 | MatchesTab | Matches list with Steam filter |
| 9 | EditLeagueModal | Edit form for admins |
| 10 | LeagueTabs | Tab container component |
| 11 | index exports | Export all new components |
| 12 | league.tsx | Update route with tabs |
| 13 | Testing | Verify implementation |
