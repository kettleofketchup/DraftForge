import { memo, useMemo } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipTrigger } from '~/components/ui/tooltip';
import { PlayerPopover } from '~/components/player';
import {
  CarrySVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
  HardSupportSVG,
} from '~/components/user/positions/icons';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { AvatarUrl, DisplayName } from '~/components/user/avatar';
import { TeamTable } from '~/components/team/teamTable/teamTable';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/index';

// Position keys
type PositionKey = 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';

// Granular selectors
const selectTeams = (state: ReturnType<typeof useUserStore.getState>) => state.tournament?.teams;
const selectCurDraftRoundCaptainPk = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.captain?.pk;
const selectCurDraftRoundCaptain = (state: ReturnType<typeof useUserStore.getState>) => state.curDraftRound?.captain;

interface PositionCoverage {
  bestRank: number;
  players: UserType[];
}

interface TeamPositionCoverageResult {
  positions: Record<PositionKey, PositionCoverage>;
  uniquePossible: boolean;
  favoriteCount: Record<PositionKey, number>;
  positionHasWarning: (pos: PositionKey) => boolean;
  assignedPositions: Set<PositionKey>;
}

const positionKeys: PositionKey[] = ['carry', 'mid', 'offlane', 'soft_support', 'hard_support'];

const positionIcons: Record<PositionKey, React.FC<{className?: string}>> = {
  carry: CarrySVG,
  mid: MidSVG,
  offlane: OfflaneSVG,
  soft_support: SoftSupportSVG,
  hard_support: HardSupportSVG,
};

// Compute position coverage for a team
const computeTeamPositionCoverage = (currentTeam: TeamType | undefined): TeamPositionCoverageResult => {
  const members = currentTeam?.members || [];

  const result: Record<PositionKey, PositionCoverage> = {
    carry: { bestRank: 6, players: [] },
    mid: { bestRank: 6, players: [] },
    offlane: { bestRank: 6, players: [] },
    soft_support: { bestRank: 6, players: [] },
    hard_support: { bestRank: 6, players: [] },
  };

  // Build position -> players mapping with ranks
  const positionPlayers: Record<PositionKey, { user: UserType; rank: number }[]> = {
    carry: [], mid: [], offlane: [], soft_support: [], hard_support: [],
  };

  for (const pos of positionKeys) {
    for (const member of members) {
      const userPositions = member.positions;
      if (!userPositions) continue;
      const rank = userPositions[pos] || 0;
      if (rank > 0) {
        positionPlayers[pos].push({ user: member, rank });
      }
    }
    // Sort by rank (best/lowest first)
    positionPlayers[pos].sort((a, b) => a.rank - b.rank);

    result[pos] = {
      bestRank: positionPlayers[pos].length > 0 ? positionPlayers[pos][0].rank : 6,
      players: positionPlayers[pos].slice(0, 3).map((p) => p.user),
    };
  }

  // Greedy assignment to check which positions can be uniquely filled
  const sortedPositions = [...positionKeys].sort(
    (a, b) => positionPlayers[a].length - positionPlayers[b].length
  );

  const assignedPlayers = new Set<number>();
  const assignedPositions = new Set<PositionKey>();

  for (const pos of sortedPositions) {
    const availablePlayers = positionPlayers[pos].filter(
      (p) => !assignedPlayers.has(p.user.pk!)
    );
    if (availablePlayers.length > 0) {
      assignedPlayers.add(availablePlayers[0].user.pk!);
      assignedPositions.add(pos);
    }
  }

  // Count favorites for tooltip info
  const favoriteCount: Record<PositionKey, number> = {
    carry: 0, mid: 0, offlane: 0, soft_support: 0, hard_support: 0,
  };
  for (const member of members) {
    const userPositions = member.positions;
    if (!userPositions) continue;
    for (const pos of positionKeys) {
      if (userPositions[pos] === 1) {
        favoriteCount[pos]++;
      }
    }
  }

  // A position has a warning if conflicts exist
  const positionHasWarning = (pos: PositionKey): boolean => {
    if (result[pos].bestRank >= 6) return false;
    if (!assignedPositions.has(pos)) return true;
    if (favoriteCount[pos] > 1) return true;

    const playersForThis = positionPlayers[pos];
    for (const { user } of playersForThis) {
      for (const otherPos of positionKeys) {
        if (otherPos === pos) continue;
        const otherPlayers = positionPlayers[otherPos];
        if (otherPlayers.length === 1 && otherPlayers[0].user.pk === user.pk) {
          if (playersForThis.length === 1) return true;
        }
      }
    }
    return false;
  };

  const coveredPositions = positionKeys.filter((pos) => result[pos].bestRank < 6);
  const uniquePossible = coveredPositions.every((pos) => assignedPositions.has(pos) && !positionHasWarning(pos));

  return { positions: result, uniquePossible, favoriteCount, positionHasWarning, assignedPositions };
};

// Single position card component
const PositionCoverageCard = memo(({
  pos,
  idx,
  coverage,
  hasWarning,
  hasUniqueAssignment,
  favoriteCount,
}: {
  pos: PositionKey;
  idx: number;
  coverage: PositionCoverage;
  hasWarning: boolean;
  hasUniqueAssignment: boolean;
  favoriteCount: number;
}) => {
  const { bestRank, players } = coverage;
  const IconComponent = positionIcons[pos];

  // Color based on coverage quality - only green/orange/red
  let colorClass: string;
  let badgeColorClass: string;
  if (bestRank >= 5) {
    colorClass = 'bg-red-900/60 border-red-500/70';
    badgeColorClass = 'bg-red-600 text-white';
  } else if (hasWarning || !hasUniqueAssignment || bestRank >= 3) {
    colorClass = 'bg-orange-900/50 border-orange-500/60';
    badgeColorClass = 'bg-orange-600 text-white';
  } else {
    colorClass = 'bg-green-900/50 border-green-500/50';
    badgeColorClass = 'bg-green-600 text-white';
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className={cn('relative flex flex-col items-center p-1.5 rounded-lg border min-w-[44px]', colorClass)}>
          {bestRank <= 5 && (
            <span className={cn(
              'absolute -top-1.5 -left-1.5 h-4 w-4 rounded-full text-[10px] font-bold flex items-center justify-center z-10',
              badgeColorClass
            )}>
              {bestRank}
            </span>
          )}
          <IconComponent className="w-5 h-5" />
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
        ) : bestRank >= 5 ? (
          <p className="text-red-400">Only as last choice ({players[0]?.username})</p>
        ) : !hasUniqueAssignment ? (
          <p className="text-orange-400">No unique player available (shared with other positions)</p>
        ) : favoriteCount > 1 ? (
          <p className="text-orange-400">Conflict: {favoriteCount} members want this as favorite</p>
        ) : hasWarning ? (
          <p className="text-orange-400">Coverage conflict on team</p>
        ) : bestRank >= 3 ? (
          <p className="text-orange-400">Best rank: {bestRank}</p>
        ) : bestRank === 1 ? (
          <p className="text-green-400">{players[0]?.username}'s favorite</p>
        ) : (
          <p className="text-green-400">Best rank: {bestRank}</p>
        )}
        {players.length > 0 && (
          <p className="text-muted-foreground mt-1">
            {players.map(p => p.username).join(', ')}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  );
});
PositionCoverageCard.displayName = 'PositionCoverageCard';

export const CurrentTeamSection = memo(() => {
  const teams = useUserStore(selectTeams);
  const curDraftRoundCaptainPk = useUserStore(selectCurDraftRoundCaptainPk);
  const curDraftRoundCaptain = useUserStore(selectCurDraftRoundCaptain);

  // Get current team
  const currentTeam = useMemo(() => {
    return teams?.find((t) => t.captain?.pk === curDraftRoundCaptainPk);
  }, [teams, curDraftRoundCaptainPk]);

  // Compute position coverage
  const teamPositionCoverage = useMemo(() => {
    return computeTeamPositionCoverage(currentTeam);
  }, [currentTeam]);

  return (
    <div className="flex-1 flex flex-col gap-2 overflow-visible">
      {/* Team Position Coverage - centered across the section */}
      <div className="flex flex-wrap justify-center items-center gap-1.5 mb-2 pt-2 overflow-visible">
        {positionKeys.map((pos, idx) => {
          const coverage = teamPositionCoverage.positions[pos];
          const { favoriteCount, positionHasWarning, assignedPositions } = teamPositionCoverage;
          const hasWarning = positionHasWarning(pos);
          const hasUniqueAssignment = assignedPositions.has(pos);

          return (
            <PositionCoverageCard
              key={pos}
              pos={pos}
              idx={idx}
              coverage={coverage}
              hasWarning={hasWarning}
              hasUniqueAssignment={hasUniqueAssignment}
              favoriteCount={favoriteCount[pos]}
            />
          );
        })}
      </div>

      {/* Team Members */}
      <div>
        <h3 className="text-xs md:text-sm font-medium text-muted-foreground mb-1 text-center lg:text-left">
          {curDraftRoundCaptain ? DisplayName(curDraftRoundCaptain) : 'Current'}'s Team
        </h3>
        <TeamTable team={currentTeam} compact useStrips />
      </div>
    </div>
  );
});

CurrentTeamSection.displayName = 'CurrentTeamSection';
