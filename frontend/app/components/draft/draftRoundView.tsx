// Redesigned draft view with pick order + current team at top
// Full screen with alternating columns on md+ (2 cols) and xl+ (3 cols)
import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { Card } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { Input } from '~/components/ui/input';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { TeamPopover } from '~/components/team';
import { PlayerPopover } from '~/components/player';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import {
  CarrySVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
  HardSupportSVG,
} from '~/components/user/positions/icons';
import { cn } from '~/lib/utils';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { AvatarUrl, DisplayName } from '~/components/user/avatar';
import { UserStrip } from '~/components/user/UserStrip';
import { ChoosePlayerButton } from './buttons/choosePlayerButtons';
import { DoublePickThreshold } from './shuffle/DoublePickThreshold';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import type { DraftRoundType, DraftType } from './types';
import type { TournamentType, TeamType } from '~/components/tournament/types';
import type { UserType } from '~/index';

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

// Context slot for shuffle draft projections
const ShuffleProjectionSlot: React.FC<{
  projected: { newTeamMmr: number; newPickOrder: number; isDoublePick: boolean };
}> = ({ projected }) => (
  <div className="hidden sm:block">
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
      // For shuffle draft, pick order is determined by team MMR (lowest first)
      const activeTeams = teams
        .filter((t) => !isTeamMaxed(t))
        .map((team) => ({
          team,
          totalMmr: getTeamMmr(team),
          isCurrent: false, // Will be set below based on sort order
          pickOrder: 0,
        }))
        .sort((a, b) => a.totalMmr - b.totalMmr);

      // In shuffle draft, the FIRST team (lowest MMR) is always "current"
      // This is the defining rule of shuffle draft
      activeTeams.forEach((t, idx) => {
        t.pickOrder = idx + 1;
        // First position (index 0) is always the current picker in shuffle
        t.isCurrent = idx === 0;
      });

      return activeTeams.slice(0, 4);
    } else {
      // For snake draft, use the draft_rounds order
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

  // Position keys that exist on the user positions object
  type PositionKey = 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';

  // Count available players by position (players who have that position ranked > 0)
  const positionCounts = useMemo(() => {
    const positionKeys: PositionKey[] = ['carry', 'mid', 'offlane', 'soft_support', 'hard_support'];
    const result: Record<PositionKey, number> = {
      carry: 0,
      mid: 0,
      offlane: 0,
      soft_support: 0,
      hard_support: 0,
    };

    for (const pos of positionKeys) {
      result[pos] = availablePlayers.filter((user) => {
        const userPositions = user.positions;
        if (!userPositions) return false;
        return (userPositions[pos] || 0) > 0;
      }).length;
    }

    return result;
  }, [availablePlayers]);

  // Team position coverage analysis
  const teamPositionCoverage = useMemo(() => {
    const positionKeys: PositionKey[] = ['carry', 'mid', 'offlane', 'soft_support', 'hard_support'];
    const members = currentTeam?.members || [];

    type PositionCoverage = {
      bestRank: number; // Lowest number = most preferred (1 = favorite, 5 = least, 6 = no one)
      players: UserType[]; // Team members who can play this position
    };

    const result: Record<PositionKey, PositionCoverage> = {
      carry: { bestRank: 6, players: [] },
      mid: { bestRank: 6, players: [] },
      offlane: { bestRank: 6, players: [] },
      soft_support: { bestRank: 6, players: [] },
      hard_support: { bestRank: 6, players: [] },
    };

    for (const pos of positionKeys) {
      const playersForPos: { user: UserType; rank: number }[] = [];

      for (const member of members) {
        const userPositions = member.positions;
        if (!userPositions) continue;
        const rank = userPositions[pos] || 0;
        if (rank > 0) {
          playersForPos.push({ user: member, rank });
        }
      }

      // Sort by rank (best/lowest first)
      playersForPos.sort((a, b) => a.rank - b.rank);

      result[pos] = {
        bestRank: playersForPos.length > 0 ? playersForPos[0].rank : 6,
        players: playersForPos.slice(0, 3).map((p) => p.user), // Top 3 players for this position
      };
    }

    // Check if unique preferred positions are possible (each member gets their #1)
    // Count how many members have each position as their #1
    const favoriteCount: Record<PositionKey, number> = {
      carry: 0, mid: 0, offlane: 0, soft_support: 0, hard_support: 0,
    };
    for (const member of members) {
      const userPositions = member.positions;
      if (!userPositions) continue;
      // Find which position is their #1 (rank = 1)
      for (const pos of positionKeys) {
        if (userPositions[pos] === 1) {
          favoriteCount[pos]++;
        }
      }
    }

    // Count positions that have conflicts (>1 person wants it)
    const conflictedPositions = positionKeys.filter((pos) => favoriteCount[pos] > 1);
    const hasConflicts = conflictedPositions.length > 0;

    // Count total unique positions claimed as favorites
    const positionsWithFavorites = positionKeys.filter((pos) => favoriteCount[pos] >= 1);

    // A position has a warning if:
    // 1. More than one person wants it (direct conflict)
    // 2. OR there are conflicts elsewhere AND this position is among the contested group
    //    (e.g., 2 people want pos 1,2,3 means one of those 3 will be unfulfilled)
    const positionHasWarning = (pos: PositionKey): boolean => {
      // Direct conflict: >1 person wants this
      if (favoriteCount[pos] > 1) return true;

      // If there are conflicts, check if total favorites > members who claimed them
      // This catches the case where 2 members both want positions from a set of 3
      if (hasConflicts && favoriteCount[pos] === 1) {
        // This position is claimed by exactly 1 person, but if there are conflicts,
        // we need to check if the total number of favorite claims exceeds available slots
        const totalFavoriteClaims = positionKeys.reduce((sum, p) => sum + favoriteCount[p], 0);
        const membersWithFavorites = members.filter((m) => {
          const up = m.positions;
          return up && positionKeys.some((p) => up[p] === 1);
        }).length;
        // If more claims than members, there's an issue
        if (totalFavoriteClaims > membersWithFavorites) return true;
      }

      return false;
    };

    // Unique is possible only if no position has warnings
    const uniquePossible = positionKeys.every((pos) => !positionHasWarning(pos));

    return { positions: result, uniquePossible, favoriteCount, positionHasWarning };
  }, [currentTeam?.members]);

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
    <div className="flex flex-col h-full gap-2 p-2 md:gap-4 md:p-4">
      {/* Top Section: Pick Order + Current Team - unified card */}
      <Card className="p-2 md:p-4 shrink-0">
        <div className="flex flex-col lg:flex-row gap-3 md:gap-4">
          {/* Pick Order - Left side */}
          <div className="shrink-0">
            <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-2 md:mb-3 text-center lg:text-left">
              Pick Order
            </h3>
            <div className="flex flex-row justify-center lg:justify-start gap-1 md:gap-1.5">
              {pickOrderCaptains.map((captain, idx) => (
                <TeamPopover key={captain.team.pk || idx} team={captain.team}>
                  <div
                    className={cn(
                      'flex flex-row md:flex-col items-center p-1 md:p-1.5 rounded-lg cursor-pointer transition-all',
                      'gap-1.5 md:gap-0',
                      'md:min-w-[70px]',
                      captain.isCurrent
                        ? 'bg-green-950/40 border-2 border-green-500'
                        : 'bg-muted/30 border border-muted hover:bg-muted/50'
                    )}
                    data-testid={`pick-order-captain-${idx}`}
                  >
                    <Badge
                      variant={captain.isCurrent ? 'default' : 'secondary'}
                      className={cn('text-[9px] md:text-[10px] px-1 md:mb-0.5', captain.isCurrent && 'bg-green-600')}
                    >
                      {captain.isCurrent ? 'NOW' : getOrdinal(captain.pickOrder)}
                    </Badge>

                    {captain.team.captain ? (
                      <img
                        src={AvatarUrl(captain.team.captain)}
                        alt={captain.team.captain?.username || 'Captain'}
                        className={cn(
                          'w-8 h-8 md:w-10 md:h-10 rounded-full transition-all shrink-0',
                          captain.isCurrent && 'ring-2 ring-green-500'
                        )}
                      />
                    ) : (
                      <div className="w-8 h-8 md:w-10 md:h-10 rounded-full bg-muted shrink-0" />
                    )}

                    {/* Mobile: inline name + MMR | Desktop: stacked below avatar */}
                    <div className="flex flex-row md:flex-col items-center md:items-center gap-1 md:gap-0">
                      <span className="text-[10px] md:text-[10px] font-medium truncate max-w-[60px] md:max-w-[65px] md:mt-0.5 md:text-center">
                        {captain.team.captain ? DisplayName(captain.team.captain) : 'No Captain'}
                      </span>
                      <span className="text-xs md:text-sm font-medium text-muted-foreground">
                        {captain.totalMmr.toLocaleString()} · {(captain.team.members?.length || 1) - 1}/4
                      </span>
                    </div>
                  </div>
                </TeamPopover>
              ))}
            </div>
          </div>

          {/* Divider */}
          <div className="hidden lg:block w-px bg-border" />

          {/* Current Team + Best by Position - Right side, visible on all screens */}
          <div className="flex-1 flex flex-col gap-2 overflow-visible">
            {/* Team Position Coverage - centered across the section */}
            <div className="flex flex-wrap justify-center items-center gap-1.5 mb-2 pt-2 overflow-visible">
              {(['carry', 'mid', 'offlane', 'soft_support', 'hard_support'] as PositionKey[]).map((pos, idx) => {
                const coverage = teamPositionCoverage.positions[pos];
                const { bestRank, players } = coverage;
                const hasFavorite = bestRank === 1;
                const { uniquePossible, favoriteCount, positionHasWarning } = teamPositionCoverage;
                const hasWarning = positionHasWarning(pos);

                // Position icon mapping
                const positionIcons: Record<PositionKey, React.FC<{className?: string}>> = {
                  carry: CarrySVG,
                  mid: MidSVG,
                  offlane: OfflaneSVG,
                  soft_support: SoftSupportSVG,
                  hard_support: HardSupportSVG,
                };

                const IconComponent = positionIcons[pos];

                // Color based on coverage quality - only green/orange/red
                // Red: no one can play (bestRank = 6) or only as worst choice (5)
                // Orange: has conflict warning OR only available as 3rd/4th choice
                // Green: someone has it as favorite AND no conflicts (unique possible), OR good coverage (1-2)
                let colorClass: string;
                let badgeColorClass: string;
                if (bestRank >= 5 || bestRank === 6) {
                  // Red: no coverage or very poor
                  colorClass = 'bg-red-900/60 border-red-500/70';
                  badgeColorClass = 'bg-red-600 text-white';
                } else if (hasWarning || bestRank >= 3) {
                  // Orange: conflicts or mediocre coverage
                  colorClass = 'bg-orange-900/50 border-orange-500/60';
                  badgeColorClass = 'bg-orange-600 text-white';
                } else {
                  // Green: good coverage (1-2) with no conflicts
                  colorClass = 'bg-green-900/50 border-green-500/50';
                  badgeColorClass = 'bg-green-600 text-white';
                }

                return (
                  <Tooltip key={pos}>
                    <TooltipTrigger asChild>
                      <div className={cn('relative flex flex-col items-center p-1.5 rounded-lg border min-w-[44px]', colorClass)}>
                        {/* Rank badge - positioned outside top-left */}
                        {bestRank <= 5 && (
                          <span className={cn(
                            'absolute -top-1.5 -left-1.5 h-4 w-4 rounded-full text-[10px] font-bold flex items-center justify-center z-10',
                            badgeColorClass
                          )}>
                            {bestRank}
                          </span>
                        )}
                        {/* Icon */}
                        <IconComponent className="w-5 h-5" />
                        {/* Player avatars */}
                        <div className="flex -space-x-1 mt-1">
                          {players.length > 0 ? (
                            players.slice(0, 3).map((player) => (
                              <PlayerPopover key={player.pk} player={player}>
                                <Avatar className="h-4 w-4 border border-background cursor-pointer">
                                  <AvatarImage src={AvatarUrl(player)} alt={player.username || ''} />
                                  <AvatarFallback className="text-[7px]">
                                    {(player.username || 'P')[0]}
                                  </AvatarFallback>
                                </Avatar>
                              </PlayerPopover>
                            ))
                          ) : (
                            <div className="h-4 w-4 rounded-full bg-muted/50 flex items-center justify-center">
                              <span className="text-[7px] text-muted-foreground">—</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-xs max-w-[200px]">
                      <p className="font-medium">Position {idx + 1}</p>
                      {bestRank === 6 ? (
                        <p className="text-red-400">No one on team plays this</p>
                      ) : bestRank === 5 ? (
                        <p className="text-red-400">Only as last choice ({players[0]?.username})</p>
                      ) : hasWarning && favoriteCount[pos] > 1 ? (
                        <p className="text-yellow-400">Conflict: {favoriteCount[pos]} members want this as favorite</p>
                      ) : hasWarning ? (
                        <p className="text-yellow-400">Position coverage conflict on team</p>
                      ) : bestRank >= 3 ? (
                        <p className="text-yellow-400">Best rank: {bestRank}</p>
                      ) : hasFavorite && uniquePossible ? (
                        <p className="text-green-400">{players[0]?.username}'s favorite</p>
                      ) : (
                        <p>Best rank: {bestRank}</p>
                      )}
                      {players.length > 0 && (
                        <p className="text-muted-foreground mt-1">
                          {players.map(p => p.username).join(', ')}
                        </p>
                      )}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>

            {/* Team Members */}
            <div>
              <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-1 text-center lg:text-left">
                {curDraftRound?.captain ? DisplayName(curDraftRound.captain) : 'Current'}'s Team
              </h3>
              <TeamTable team={currentTeam} compact useStrips />
            </div>
          </div>
        </div>
      </Card>

      {/* Double Pick Threshold for shuffle - more compact */}
      {isShuffle && (
        <div className="shrink-0">
          <DoublePickThreshold />
        </div>
      )}

      {/* Bottom Section: Available Players */}
      <div className="flex-1 min-h-[180px] md:min-h-[250px] flex flex-col">
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
                  {col1.map((user) => {
                    const projected = getProjectedData(user.mmr || 0);
                    return (
                      <UserStrip
                        key={user.pk}
                        user={user}
                        className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                        contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                        actionSlot={<ChoosePlayerButton user={user} />}
                        data-testid="available-player"
                      />
                    );
                  })}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {col2.map((user) => {
                    const projected = getProjectedData(user.mmr || 0);
                    return (
                      <UserStrip
                        key={user.pk}
                        user={user}
                        className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                        contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                        actionSlot={<ChoosePlayerButton user={user} />}
                        data-testid="available-player"
                      />
                    );
                  })}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {col3.map((user) => {
                    const projected = getProjectedData(user.mmr || 0);
                    return (
                      <UserStrip
                        key={user.pk}
                        user={user}
                        className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                        contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                        actionSlot={<ChoosePlayerButton user={user} />}
                        data-testid="available-player"
                      />
                    );
                  })}
                </div>
              </ScrollArea>
            </div>

            {/* Medium-Large screens: Two columns */}
            <div className="hidden md:grid xl:hidden md:grid-cols-2 gap-2 flex-1 min-h-0">
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {leftCol.map((user) => {
                    const projected = getProjectedData(user.mmr || 0);
                    return (
                      <UserStrip
                        key={user.pk}
                        user={user}
                        className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                        contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                        actionSlot={<ChoosePlayerButton user={user} />}
                        data-testid="available-player"
                      />
                    );
                  })}
                </div>
              </ScrollArea>
              <ScrollArea className="h-full">
                <div className="space-y-1.5 pr-2">
                  {rightCol.map((user) => {
                    const projected = getProjectedData(user.mmr || 0);
                    return (
                      <UserStrip
                        key={user.pk}
                        user={user}
                        className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                        contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                        actionSlot={<ChoosePlayerButton user={user} />}
                        data-testid="available-player"
                      />
                    );
                  })}
                </div>
              </ScrollArea>
            </div>

            {/* Small screens: Single column */}
            <ScrollArea className="md:hidden flex-1">
              <div className="space-y-1.5 pr-2">
                {filteredPlayers.map((user) => {
                  const projected = getProjectedData(user.mmr || 0);
                  return (
                    <UserStrip
                      key={user.pk}
                      user={user}
                      className={projected?.isDoublePick ? 'bg-green-950/30 border-green-500/50' : undefined}
                      contextSlot={isShuffle && projected ? <ShuffleProjectionSlot projected={projected} /> : undefined}
                      actionSlot={<ChoosePlayerButton user={user} />}
                      data-testid="available-player"
                    />
                  );
                })}
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
};

export default DraftRoundView;
