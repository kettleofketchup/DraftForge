// Redesigned draft view with pick order + current team at top
// Full screen with alternating columns on md+ (2 cols) and xl+ (3 cols)
import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { Card } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { Input } from '~/components/ui/input';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Separator } from '~/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { Avatar, AvatarImage, AvatarFallback } from '~/components/ui/avatar';
import { TeamPopover } from '~/components/team';
import { PlayerPopover } from '~/components/player';
import { cn } from '~/lib/utils';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { AvatarUrl, DisplayName } from '~/components/user/avatar';
import { RolePositions } from '../user/positions';
import { ChoosePlayerButton } from './buttons/choosePlayerButtons';
import { DoublePickThreshold } from './shuffle/DoublePickThreshold';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import type { DraftRoundType, DraftType, TournamentType } from './types';
import type { TeamType, UserType } from '~/index';

// Filter types
type PositionFilter = 'all' | 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';
type PickOrderFilter = 'all' | 'double_pick' | 'maintains_first';
type LeagueStatsFilter = 'all' | 'high_winrate' | 'experienced' | 'new_players';

const POSITION_LABELS: Record<PositionFilter, string> = {
  all: 'All',
  carry: 'Pos 1',
  mid: 'Pos 2',
  offlane: 'Pos 3',
  soft_support: 'Pos 4',
  hard_support: 'Pos 5',
};

const PICK_ORDER_LABELS: Record<PickOrderFilter, string> = {
  all: 'All',
  double_pick: 'Double Pick',
  maintains_first: 'Stay 1st',
};

const LEAGUE_STATS_LABELS: Record<LeagueStatsFilter, string> = {
  all: 'All',
  high_winrate: 'High WR',
  experienced: '10+ Games',
  new_players: 'New',
};

const log = getLogger('DraftRoundView');
const MAX_TEAM_SIZE = 5;

// Helper to get ordinal suffix
const getOrdinal = (n: number): string => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

interface PickOrderCaptain {
  team: TeamType;
  totalMmr: number;
  isCurrent: boolean;
  pickOrder: number;
}

// Player row component - compact card design
const PlayerRow: React.FC<{
  user: UserType;
  projected: { newTeamMmr: number; newPickOrder: number; isDoublePick: boolean } | null;
  isShuffle: boolean;
}> = ({ user, projected, isShuffle }) => (
  <div
    className={cn(
      'flex items-center gap-2 p-2 rounded-lg border transition-colors',
      projected?.isDoublePick
        ? 'bg-green-950/30 border-green-500/50'
        : 'bg-muted/20 border-muted hover:bg-muted/40'
    )}
    data-testid={`player-row-${user.pk}`}
  >
    {/* Avatar */}
    <PlayerPopover player={user}>
      <Avatar className="h-8 w-8 cursor-pointer shrink-0">
        <AvatarImage src={AvatarUrl(user)} alt={user.username || 'Player'} />
        <AvatarFallback>{(user.username || 'P')[0].toUpperCase()}</AvatarFallback>
      </Avatar>
    </PlayerPopover>

    {/* Player Info */}
    <div className="flex-1 min-w-0">
      <PlayerPopover player={user}>
        <span className="text-sm font-medium truncate block cursor-pointer hover:text-primary transition-colors">
          {DisplayName(user)}
        </span>
      </PlayerPopover>
      <div className="flex items-center gap-1 text-xs flex-wrap">
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" className="px-1.5 py-0.5 text-[11px] font-mono shrink-0 cursor-help">
              <span className="text-muted-foreground">B:</span>
              <span className="ml-0.5">{user.mmr?.toLocaleString() || '—'}</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs bg-popover text-popover-foreground">
            <p className="font-semibold text-foreground">Base MMR</p>
            <p className="text-muted-foreground">Dota 2 ranked MMR</p>
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="secondary" className="px-1.5 py-0.5 text-[11px] font-mono shrink-0 cursor-help bg-primary/20">
              <span className="text-muted-foreground">L:</span>
              <span className="ml-0.5">{(user as UserType & { league_mmr?: number }).league_mmr?.toLocaleString() || '—'}</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs bg-popover text-popover-foreground">
            <p className="font-semibold text-foreground">League MMR</p>
            <p className="text-muted-foreground">Performance-adjusted rating</p>
          </TooltipContent>
        </Tooltip>
        <Separator orientation="vertical" className="h-3 mx-0.5 hidden sm:block" />
        <RolePositions user={user} compact disableTooltips />
      </div>
    </div>

    {/* Shuffle projection (hidden on small screens) */}
    {isShuffle && projected && (
      <div className="text-right text-xs hidden sm:block shrink-0">
        <div className="text-muted-foreground">
          → {projected.newTeamMmr.toLocaleString()}
        </div>
        <div
          className={cn(
            projected.isDoublePick
              ? 'text-green-400 font-medium'
              : 'text-muted-foreground'
          )}
        >
          {getOrdinal(projected.newPickOrder)}
          {projected.isDoublePick && ' 🔥'}
        </div>
      </div>
    )}

    {/* Pick Button */}
    <div className="shrink-0">
      <ChoosePlayerButton user={user} />
    </div>
  </div>
);

export const DraftRoundView: React.FC = () => {
  const curDraftRound: DraftRoundType = useUserStore((state) => state.curDraftRound);
  const draftIndex: number = useUserStore((state) => state.draftIndex);
  const tournament: TournamentType = useUserStore((state) => state.tournament);
  const draft: DraftType = useUserStore((state) => state.draft);

  useEffect(() => {
    log.debug('Current draft round changed:', curDraftRound);
  }, [draftIndex]);

  const latestRound = () =>
    draft?.draft_rounds?.find(
      (round: DraftRoundType) => round.pk === draft?.latest_round,
    );

  // Calculate team MMR
  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member: UserType) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const isTeamMaxed = (team: TeamType): boolean => {
    return (team.members?.length || 0) >= MAX_TEAM_SIZE;
  };

  // Get next 4 captains in pick order
  const pickOrderCaptains = useMemo((): PickOrderCaptain[] => {
    const teams = tournament?.teams || [];
    const isShuffle = draft?.draft_style === 'shuffle';

    if (isShuffle) {
      const activeTeams = teams
        .filter((t) => !isTeamMaxed(t))
        .map((team) => ({
          team,
          totalMmr: getTeamMmr(team),
          isCurrent: curDraftRound?.captain?.pk === team.captain?.pk,
          pickOrder: 0,
        }))
        .sort((a, b) => a.totalMmr - b.totalMmr);

      activeTeams.forEach((t, idx) => {
        t.pickOrder = idx + 1;
      });

      return activeTeams.slice(0, 4);
    } else {
      const currentRoundIndex = draft?.draft_rounds?.findIndex(
        (r: DraftRoundType) => r.pk === curDraftRound?.pk
      ) ?? 0;

      const upcomingRounds = draft?.draft_rounds?.slice(currentRoundIndex, currentRoundIndex + 4) || [];

      return upcomingRounds.map((round: DraftRoundType, idx: number) => {
        const team = teams.find((t) => t.captain?.pk === round.captain?.pk);
        return {
          team: team || ({} as TeamType),
          totalMmr: team ? getTeamMmr(team) : 0,
          isCurrent: idx === 0,
          pickOrder: idx + 1,
        };
      });
    }
  }, [tournament?.teams, draft?.draft_style, draft?.draft_rounds, curDraftRound?.pk]);

  // Get current team
  const currentTeam = useMemo(() => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curDraftRound?.captain?.pk
    );
  }, [tournament?.teams, curDraftRound?.captain?.pk]);

  // Get available players sorted by MMR
  const availablePlayers = useMemo(() => {
    return (
      draft?.users_remaining?.sort((a: UserType, b: UserType): number => {
        if (!a.mmr && !b.mmr) return 0;
        if (!a.mmr) return 1;
        if (!b.mmr) return -1;
        if (a.mmr === b.mmr) {
          return (a.username || '').localeCompare(b.username || '');
        }
        return b.mmr - a.mmr;
      }) || []
    );
  }, [draft?.users_remaining]);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [positionFilter, setPositionFilter] = useState<PositionFilter>('all');
  const [pickOrderFilter, setPickOrderFilter] = useState<PickOrderFilter>('all');
  const [leagueStatsFilter, setLeagueStatsFilter] = useState<LeagueStatsFilter>('all');

  // Helper to check if a player would result in double pick
  const wouldDoublePick = (userMmr: number): boolean => {
    if (!currentTeam) return false;
    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;
    const otherActiveTeams = (tournament?.teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));
    if (otherActiveTeams.length === 0) return true;
    const lowestOtherMmr = Math.min(...otherActiveTeams.map((t) => getTeamMmr(t)));
    const wouldBeMaxed = (currentTeam.members?.length || 0) + 1 >= MAX_TEAM_SIZE;
    return !wouldBeMaxed && newTeamMmr < lowestOtherMmr;
  };

  // Helper to check if picking would maintain first pick
  const wouldMaintainFirst = (userMmr: number): boolean => {
    if (!currentTeam) return false;
    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;
    const otherActiveTeams = (tournament?.teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));
    if (otherActiveTeams.length === 0) return true;
    const lowestOtherMmr = Math.min(...otherActiveTeams.map((t) => getTeamMmr(t)));
    return newTeamMmr <= lowestOtherMmr;
  };

  // Filter players by all criteria
  const filteredPlayers = useMemo(() => {
    let players = availablePlayers;

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      players = players.filter((user) =>
        (user.username || '').toLowerCase().includes(query) ||
        (user.nickname || '').toLowerCase().includes(query)
      );
    }

    // Position filter
    if (positionFilter !== 'all') {
      players = players.filter((user) => {
        const positions = user.positions;
        if (!positions) return false;
        return (positions[positionFilter] || 0) > 0;
      });
    }

    // Pick order filter (shuffle only)
    if (draft?.draft_style === 'shuffle' && pickOrderFilter !== 'all') {
      players = players.filter((user) => {
        const mmr = user.mmr || 0;
        if (pickOrderFilter === 'double_pick') return wouldDoublePick(mmr);
        if (pickOrderFilter === 'maintains_first') return wouldMaintainFirst(mmr);
        return true;
      });
    }

    // League stats filter
    if (leagueStatsFilter !== 'all') {
      players = players.filter((user) => {
        const extended = user as UserType & { games_played?: number; win_rate?: number };
        if (leagueStatsFilter === 'high_winrate') return (extended.win_rate || 0) >= 55;
        if (leagueStatsFilter === 'experienced') return (extended.games_played || 0) >= 10;
        if (leagueStatsFilter === 'new_players') return (extended.games_played || 0) < 5;
        return true;
      });
    }

    return players;
  }, [availablePlayers, searchQuery, positionFilter, pickOrderFilter, leagueStatsFilter, draft?.draft_style]);

  // Split players into columns (newspaper style)
  const { col1, col2, col3, leftCol, rightCol } = useMemo(() => {
    // 3-column split for XL
    const threeCol: [UserType[], UserType[], UserType[]] = [[], [], []];
    filteredPlayers.forEach((player, idx) => {
      threeCol[idx % 3].push(player);
    });
    // 2-column split for MD-LG
    const twoCol: [UserType[], UserType[]] = [[], []];
    filteredPlayers.forEach((player, idx) => {
      twoCol[idx % 2].push(player);
    });
    return {
      col1: threeCol[0],
      col2: threeCol[1],
      col3: threeCol[2],
      leftCol: twoCol[0],
      rightCol: twoCol[1],
    };
  }, [filteredPlayers]);

  // Projected data for shuffle mode
  const getProjectedData = (userMmr: number) => {
    if (draft?.draft_style !== 'shuffle' || !currentTeam) return null;

    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;

    const otherActiveTeams = (tournament?.teams || [])
      .filter((t) => t.pk !== currentTeam.pk && !isTeamMaxed(t));

    if (otherActiveTeams.length === 0) {
      return { newTeamMmr, newPickOrder: 1, isDoublePick: true };
    }

    const otherMmrs = otherActiveTeams.map((t) => getTeamMmr(t));
    const allMmrs = [...otherMmrs, newTeamMmr].sort((a, b) => a - b);
    const newPickOrder = allMmrs.indexOf(newTeamMmr) + 1;

    const wouldBeMaxedAfterPick = (currentTeam.members?.length || 0) + 1 >= MAX_TEAM_SIZE;
    const lowestOtherMmr = Math.min(...otherMmrs);
    const isDoublePick = !wouldBeMaxedAfterPick && newTeamMmr < lowestOtherMmr;

    return { newTeamMmr, newPickOrder, isDoublePick };
  };

  if (!draft || !draft.draft_rounds) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-bold">No Draft Information Available</h1>
          <p className="text-muted-foreground">Start the draft with the init draft button below</p>
        </div>
      </div>
    );
  }

  const isNotLatestRound =
    draft?.latest_round &&
    draft?.latest_round !== curDraftRound?.pk &&
    !curDraftRound?.choice;

  if (isNotLatestRound) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h3 className="text-xl font-bold">Not Current Round</h3>
          <p className="text-muted-foreground">
            Pick {curDraftRound?.pick_number} of {latestRound()?.pick_number}
          </p>
        </div>
      </div>
    );
  }

  const isShuffle = draft?.draft_style === 'shuffle';

  return (
    <div className="flex flex-col h-full gap-4 p-4">
      {/* Top Section: Pick Order + Current Team */}
      <div className="flex flex-col md:flex-row gap-4 shrink-0">
        {/* Pick Order - Left on desktop, first on mobile */}
        <Card className="flex-1 p-4">
          <h3 className="text-sm font-medium text-muted-foreground mb-3 text-center md:text-left">
            Pick Order
          </h3>
          <div className="flex flex-row justify-center md:justify-start gap-2 flex-wrap">
            {pickOrderCaptains.map((captain, idx) => (
              <TeamPopover key={captain.team.pk || idx} team={captain.team}>
                <div
                  className={cn(
                    'flex flex-col items-center p-2 rounded-lg min-w-[80px] cursor-pointer transition-all',
                    captain.isCurrent
                      ? 'bg-green-950/40 border-2 border-green-500'
                      : 'bg-muted/30 border border-muted hover:bg-muted/50'
                  )}
                  data-testid={`pick-order-captain-${idx}`}
                >
                  <Badge
                    variant={captain.isCurrent ? 'default' : 'secondary'}
                    className={cn('mb-1 text-xs', captain.isCurrent && 'bg-green-600')}
                  >
                    {captain.isCurrent ? 'NOW' : getOrdinal(captain.pickOrder)}
                  </Badge>

                  {captain.team.captain ? (
                    <img
                      src={AvatarUrl(captain.team.captain)}
                      alt={captain.team.captain?.username || 'Captain'}
                      className={cn(
                        'w-12 h-12 rounded-full transition-all',
                        captain.isCurrent && 'ring-2 ring-green-500'
                      )}
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-muted" />
                  )}

                  <span className="text-xs font-medium mt-1 text-center truncate max-w-[70px]">
                    {captain.team.captain ? DisplayName(captain.team.captain) : 'No Captain'}
                  </span>

                  <span className="text-[10px] text-muted-foreground">
                    {captain.totalMmr.toLocaleString()} MMR
                  </span>
                </div>
              </TeamPopover>
            ))}
          </div>
        </Card>

        {/* Current Team - Right on desktop, second on mobile */}
        <Card className="flex-1 p-4 max-h-[220px] overflow-auto">
          <h3 className="text-sm font-medium text-muted-foreground mb-2 text-center md:text-left">
            {curDraftRound?.captain ? DisplayName(curDraftRound.captain) : 'Current'}'s Team
          </h3>
          <TeamTable team={currentTeam} />
        </Card>
      </div>

      {/* Double Pick Threshold for shuffle */}
      {isShuffle && (
        <div className="shrink-0">
          <DoublePickThreshold />
        </div>
      )}

      {/* Bottom Section: Available Players */}
      <div className="flex-1 min-h-0 flex flex-col">
        {curDraftRound?.choice ? (
          <Card className="h-full flex items-center justify-center">
            <p className="text-lg font-semibold text-green-400">
              Picked: {DisplayName(curDraftRound.choice)}
            </p>
          </Card>
        ) : (
          <>
            {/* Search + Filter Tabs */}
            <div className="shrink-0 space-y-2 mb-3">
              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search players..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-8 text-sm"
                />
              </div>

              {/* Filter Tabs */}
              <Tabs defaultValue="positions" className="w-full">
                <TabsList className="grid w-full grid-cols-3 h-8">
                  <TabsTrigger value="positions" className="text-xs">Positions</TabsTrigger>
                  {isShuffle && <TabsTrigger value="pickorder" className="text-xs">Pick Order</TabsTrigger>}
                  {!isShuffle && <TabsTrigger value="pickorder" disabled className="text-xs opacity-50">Pick Order</TabsTrigger>}
                  <TabsTrigger value="league" className="text-xs">League</TabsTrigger>
                </TabsList>

                <TabsContent value="positions" className="mt-2">
                  <div className="flex flex-wrap gap-1">
                    {(Object.keys(POSITION_LABELS) as PositionFilter[]).map((pos) => (
                      <Button
                        key={pos}
                        size="sm"
                        variant={positionFilter === pos ? 'default' : 'outline'}
                        onClick={() => setPositionFilter(pos)}
                        className="text-xs px-2 py-0.5 h-6"
                      >
                        {POSITION_LABELS[pos]}
                      </Button>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="pickorder" className="mt-2">
                  <div className="flex flex-wrap gap-1">
                    {(Object.keys(PICK_ORDER_LABELS) as PickOrderFilter[]).map((filter) => (
                      <Button
                        key={filter}
                        size="sm"
                        variant={pickOrderFilter === filter ? 'default' : 'outline'}
                        onClick={() => setPickOrderFilter(filter)}
                        className="text-xs px-2 py-0.5 h-6"
                      >
                        {PICK_ORDER_LABELS[filter]}
                      </Button>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="league" className="mt-2">
                  <div className="flex flex-wrap gap-1">
                    {(Object.keys(LEAGUE_STATS_LABELS) as LeagueStatsFilter[]).map((filter) => (
                      <Button
                        key={filter}
                        size="sm"
                        variant={leagueStatsFilter === filter ? 'default' : 'outline'}
                        onClick={() => setLeagueStatsFilter(filter)}
                        className="text-xs px-2 py-0.5 h-6"
                      >
                        {LEAGUE_STATS_LABELS[filter]}
                      </Button>
                    ))}
                  </div>
                </TabsContent>
              </Tabs>

              <div className="text-xs text-muted-foreground">
                {filteredPlayers.length} players
              </div>
            </div>

            {/* XL screens: Three columns */}
            <div className="hidden xl:grid xl:grid-cols-3 gap-2 flex-1 min-h-0">
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {col1.map((user) => (
                    <PlayerRow
                      key={user.pk}
                      user={user}
                      projected={getProjectedData(user.mmr || 0)}
                      isShuffle={isShuffle}
                    />
                  ))}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {col2.map((user) => (
                    <PlayerRow
                      key={user.pk}
                      user={user}
                      projected={getProjectedData(user.mmr || 0)}
                      isShuffle={isShuffle}
                    />
                  ))}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {col3.map((user) => (
                    <PlayerRow
                      key={user.pk}
                      user={user}
                      projected={getProjectedData(user.mmr || 0)}
                      isShuffle={isShuffle}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Medium-Large screens: Two columns */}
            <div className="hidden md:grid xl:hidden md:grid-cols-2 gap-2 flex-1 min-h-0">
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {leftCol.map((user) => (
                    <PlayerRow
                      key={user.pk}
                      user={user}
                      projected={getProjectedData(user.mmr || 0)}
                      isShuffle={isShuffle}
                    />
                  ))}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {rightCol.map((user) => (
                    <PlayerRow
                      key={user.pk}
                      user={user}
                      projected={getProjectedData(user.mmr || 0)}
                      isShuffle={isShuffle}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Small screens: Single column */}
            <ScrollArea className="md:hidden flex-1">
              <div className="space-y-1.5 pr-2">
                {filteredPlayers.map((user) => (
                  <PlayerRow
                    key={user.pk}
                    user={user}
                    projected={getProjectedData(user.mmr || 0)}
                    isShuffle={isShuffle}
                  />
                ))}
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
};

export default DraftRoundView;
