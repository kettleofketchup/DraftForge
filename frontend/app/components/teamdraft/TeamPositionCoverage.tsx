// frontend/app/components/teamdraft/TeamPositionCoverage.tsx
import { memo, useCallback, useMemo, useState } from 'react';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '~/components/ui/hover-card';
import { InfoDialog } from '~/components/ui/dialogs';
import {
  CarrySVG,
  MidSVG,
  OfflaneSVG,
  SoftSupportSVG,
  HardSupportSVG,
} from '~/components/user/positions/icons';
import { UserAvatar } from '~/components/user/UserAvatar';
import { PlayerPopover } from '~/components/player';
import { cn } from '~/lib/utils';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';

// Position keys
export type PositionKey = 'carry' | 'mid' | 'offlane' | 'soft_support' | 'hard_support';

export interface PlayerWithRank {
  user: UserType;
  rank: number;
}

export interface PositionCoverage {
  bestRank: number;
  players: UserType[];
  playersWithRanks: PlayerWithRank[];
  conflicts: string[];
  possibleMMR: number; // Average MMR of players who can play this position
}

export interface TeamPositionCoverageResult {
  positions: Record<PositionKey, PositionCoverage>;
  uniquePossible: boolean;
  favoriteCount: Record<PositionKey, number>;
  positionHasWarning: (pos: PositionKey) => boolean;
  assignedPositions: Set<PositionKey>;
  /** Map of position -> assigned player pk (for display ordering) */
  positionAssignments: Map<PositionKey, number>;
}

export const positionKeys: PositionKey[] = ['carry', 'mid', 'offlane', 'soft_support', 'hard_support'];

export const positionIcons: Record<PositionKey, React.FC<{className?: string}>> = {
  carry: CarrySVG,
  mid: MidSVG,
  offlane: OfflaneSVG,
  soft_support: SoftSupportSVG,
  hard_support: HardSupportSVG,
};

const positionLabels: Record<PositionKey, string> = {
  carry: 'Pos 1',
  mid: 'Pos 2',
  offlane: 'Pos 3',
  soft_support: 'Pos 4',
  hard_support: 'Pos 5',
};

// Compute position coverage for a team
export const computeTeamPositionCoverage = (currentTeam: TeamType | undefined): TeamPositionCoverageResult => {
  const members = currentTeam?.members || [];

  const result: Record<PositionKey, PositionCoverage> = {
    carry: { bestRank: 6, players: [], playersWithRanks: [], conflicts: [], possibleMMR: 0 },
    mid: { bestRank: 6, players: [], playersWithRanks: [], conflicts: [], possibleMMR: 0 },
    offlane: { bestRank: 6, players: [], playersWithRanks: [], conflicts: [], possibleMMR: 0 },
    soft_support: { bestRank: 6, players: [], playersWithRanks: [], conflicts: [], possibleMMR: 0 },
    hard_support: { bestRank: 6, players: [], playersWithRanks: [], conflicts: [], possibleMMR: 0 },
  };

  // Build position -> players mapping with ranks
  const positionPlayers: Record<PositionKey, PlayerWithRank[]> = {
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

    // Calculate average MMR for players who can play this position
    const playersForPos = positionPlayers[pos];
    const possibleMMR = playersForPos.length > 0
      ? Math.round(playersForPos.reduce((sum, p) => sum + (p.user.mmr || 0), 0) / playersForPos.length)
      : 0;

    result[pos] = {
      bestRank: playersForPos.length > 0 ? playersForPos[0].rank : 6,
      players: playersForPos.slice(0, 3).map((p) => p.user),
      playersWithRanks: playersForPos,
      conflicts: [],
      possibleMMR,
    };
  }

  // Greedy assignment to check which positions can be uniquely filled
  // Sort by fewest options first (most constrained positions get assigned first)
  const sortedPositions = [...positionKeys].sort(
    (a, b) => positionPlayers[a].length - positionPlayers[b].length
  );

  const assignedPlayers = new Set<number>();
  const assignedPositions = new Set<PositionKey>();
  // Track which player is assigned to which position
  const positionAssignments = new Map<PositionKey, number>(); // position -> player pk
  const playerAssignments = new Map<number, PositionKey>(); // player pk -> position

  for (const pos of sortedPositions) {
    const availablePlayers = positionPlayers[pos].filter(
      (p) => !assignedPlayers.has(p.user.pk!)
    );
    if (availablePlayers.length > 0) {
      const assignedPlayer = availablePlayers[0];
      assignedPlayers.add(assignedPlayer.user.pk!);
      assignedPositions.add(pos);
      positionAssignments.set(pos, assignedPlayer.user.pk!);
      playerAssignments.set(assignedPlayer.user.pk!, pos);
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

  // Find contested positions: positions that share the same top players
  const contestedPositions = new Map<PositionKey, PositionKey[]>();
  for (const pos of positionKeys) {
    const playersForPos = positionPlayers[pos];
    if (playersForPos.length === 0) continue;

    const topPlayerPks = new Set(playersForPos.slice(0, 2).map(p => p.user.pk));

    for (const otherPos of positionKeys) {
      if (otherPos === pos) continue;
      const otherPlayers = positionPlayers[otherPos];
      if (otherPlayers.length === 0) continue;

      // Check if top players overlap significantly
      const otherTopPks = new Set(otherPlayers.slice(0, 2).map(p => p.user.pk));
      const overlap = [...topPlayerPks].filter(pk => otherTopPks.has(pk));

      if (overlap.length >= 2 || (overlap.length === 1 && topPlayerPks.size <= 2 && otherTopPks.size <= 2)) {
        const existing = contestedPositions.get(pos) || [];
        if (!existing.includes(otherPos)) {
          contestedPositions.set(pos, [...existing, otherPos]);
        }
      }
    }
  }

  // Build conflict/status messages for each position
  for (const pos of positionKeys) {
    const messages: string[] = [];
    const playersForPos = positionPlayers[pos];

    if (playersForPos.length === 0) {
      messages.push('No coverage');
    } else {
      const hasUniqueAssignment = assignedPositions.has(pos);
      const contestedWith = contestedPositions.get(pos) || [];
      const isContested = contestedWith.length > 0;

      // Check for favorite conflicts (multiple people want this as #1)
      if (favoriteCount[pos] > 1) {
        const favoritePlayers = playersForPos
          .filter(p => p.rank === 1)
          .map(p => p.user.nickname || p.user.username);
        messages.push(`${favoritePlayers.join(' & ')} both want this`);
      }

      // Check if position is contested with other positions
      if (isContested) {
        // Show each player's contest situation
        for (const player of playersForPos.slice(0, 2)) {
          const playerName = player.user.nickname || player.user.username;
          const playerContestedPositions: string[] = [];

          for (const otherPos of contestedWith) {
            const otherPlayers = positionPlayers[otherPos];
            if (otherPlayers.some(p => p.user.pk === player.user.pk)) {
              playerContestedPositions.push(positionLabels[otherPos]);
            }
          }

          if (playerContestedPositions.length > 0) {
            messages.push(`${playerName} contesting ${playerContestedPositions.join(' & ')}`);
          }
        }

        // Show who was selected as best suitability
        const assignedPlayerPk = positionAssignments.get(pos);
        const assignedPlayer = playersForPos.find(p => p.user.pk === assignedPlayerPk);
        if (assignedPlayer) {
          const playerName = assignedPlayer.user.nickname || assignedPlayer.user.username;
          if (assignedPlayer.rank === 1) {
            messages.push(`${playerName} guessed - unique & favorite`);
          } else {
            messages.push(`${playerName} guessed as best suitability`);
          }
        }
      }

      // Check if position can't be uniquely assigned
      if (!hasUniqueAssignment && playersForPos.length > 0 && !isContested) {
        // Find why - all players are needed elsewhere
        const playerConflicts: string[] = [];
        for (const { user } of playersForPos) {
          const otherPositionsNeeded: string[] = [];
          for (const otherPos of positionKeys) {
            if (otherPos === pos) continue;
            const otherPlayers = positionPlayers[otherPos];
            if (otherPlayers.length > 0 && otherPlayers[0].user.pk === user.pk) {
              otherPositionsNeeded.push(positionLabels[otherPos]);
            }
          }
          if (otherPositionsNeeded.length > 0) {
            playerConflicts.push(`${user.nickname || user.username} needed for ${otherPositionsNeeded.join(', ')}`);
          }
        }
        if (playerConflicts.length > 0) {
          messages.push(...playerConflicts);
        } else {
          messages.push('No unique player available');
        }
      }

      // Check for low rank coverage
      if (result[pos].bestRank >= 4 && messages.length === 0) {
        messages.push(`Best rank is ${result[pos].bestRank} (low preference)`);
      }

      // If no issues, no contests, and has unique assignment, show positive message
      if (messages.length === 0 && hasUniqueAssignment && !isContested) {
        const assignedPlayerPk = positionAssignments.get(pos);
        const assignedPlayer = playersForPos.find(p => p.user.pk === assignedPlayerPk);

        if (assignedPlayer) {
          const playerName = assignedPlayer.user.nickname || assignedPlayer.user.username;
          if (assignedPlayer.rank === 1) {
            messages.push(`${playerName} - unique & favorite`);
          } else {
            messages.push(`${playerName} - unique availability`);
          }
        }
      }

      // Check if best player for this position was guessed elsewhere
      if (hasUniqueAssignment && playersForPos.length > 0 && !isContested) {
        const bestPlayer = playersForPos[0];
        const bestPlayerAssignedTo = playerAssignments.get(bestPlayer.user.pk!);
        if (bestPlayerAssignedTo && bestPlayerAssignedTo !== pos) {
          const playerName = bestPlayer.user.nickname || bestPlayer.user.username;
          messages.push(`${playerName} guessed for ${positionLabels[bestPlayerAssignedTo]}`);
        }
      }
    }

    result[pos].conflicts = messages;
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

  return { positions: result, uniquePossible, favoriteCount, positionHasWarning, assignedPositions, positionAssignments };
};

// Single position card component (no tooltip - tooltip info shown in HoverCard table)
export const PositionCoverageCard = memo(({
  pos,
  idx,
  coverage,
  hasWarning,
  hasUniqueAssignment,
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
            <UserAvatar
              key={player.pk}
              user={player}
              size="tiny"
              border="muted"
            />
          ))
        ) : (
          <div className="h-4 w-4 rounded-full bg-muted/50 flex items-center justify-center">
            <span className="text-[7px] text-muted-foreground">—</span>
          </div>
        )}
      </div>
    </div>
  );
});
PositionCoverageCard.displayName = 'PositionCoverageCard';

// Single Player Card - shows avatar with name above and MMR below
const PlayerCard = memo(({ player, isBest }: { player: PlayerWithRank; isBest?: boolean }) => {
  const { user, rank } = player;
  const displayName = user.nickname || user.username || '?';

  return (
    <div className={cn(
      "flex flex-col items-center gap-0.5 min-w-[3.5rem]",
      isBest ? "opacity-100" : "opacity-60"
    )}>
      {/* Name badge above */}
      <span className={cn(
        "text-[9px] font-medium px-1.5 py-0.5 rounded truncate max-w-full text-center",
        isBest ? "text-white bg-slate-600/80" : "text-slate-300 bg-slate-700/60"
      )}>
        {displayName.length > 6 ? `${displayName.slice(0, 5)}…` : displayName}
      </span>
      {/* Avatar with rank badge - wrapped in PlayerPopover for hover */}
      <PlayerPopover player={user}>
        <div className="relative">
          <UserAvatar user={user} size="sm" border={isBest ? "primary" : "muted"} />
          <span className={cn(
            "absolute -top-1 -right-1 h-4 w-4 rounded-full text-[9px] font-bold flex items-center justify-center",
            isBest ? "bg-primary text-primary-foreground" : "bg-slate-600 text-slate-200"
          )}>
            {rank}
          </span>
        </div>
      </PlayerPopover>
      {/* MMR badge below */}
      <span className="text-[9px] font-medium text-slate-300 bg-slate-700/80 px-1.5 py-0.5 rounded">
        {user.mmr?.toLocaleString() || '—'}
      </span>
    </div>
  );
});
PlayerCard.displayName = 'PlayerCard';

// Best Players Row - shows assigned player first, then others by rank
const BestPlayersRow = memo(({
  players,
  assignedPlayerPk,
  maxDisplay = 3
}: {
  players: PlayerWithRank[];
  assignedPlayerPk?: number;
  maxDisplay?: number;
}) => {
  if (players.length === 0) {
    return (
      <div className="flex items-center justify-center min-w-[3.5rem] h-16">
        <span className="text-[9px] text-muted-foreground">—</span>
      </div>
    );
  }

  // Sort: assigned player first, then by rank
  const sortedPlayers = useMemo(() => {
    return [...players].sort((a, b) => {
      // Assigned player always comes first
      if (a.user.pk === assignedPlayerPk) return -1;
      if (b.user.pk === assignedPlayerPk) return 1;
      // Then sort by rank (lower rank = higher priority)
      return a.rank - b.rank;
    });
  }, [players, assignedPlayerPk]);

  const displayPlayers = sortedPlayers.slice(0, maxDisplay);

  return (
    <div className="flex items-end gap-1">
      {displayPlayers.map((player, idx) => (
        <PlayerCard
          key={player.user.pk}
          player={player}
          isBest={player.user.pk === assignedPlayerPk || (idx === 0 && !assignedPlayerPk)}
        />
      ))}
    </div>
  );
});
BestPlayersRow.displayName = 'BestPlayersRow';

// Position Conflict Table - shows all positions with conflicts
interface PositionConflictTableProps {
  teamPositionCoverage: TeamPositionCoverageResult;
}

const PositionConflictTable = memo(({ teamPositionCoverage }: PositionConflictTableProps) => {
  const { positions, positionHasWarning, assignedPositions, positionAssignments } = teamPositionCoverage;

  return (
    <div className="space-y-1">
      {/* Header Row - hidden on very small screens, shown on sm+ */}
      <div className="hidden sm:flex items-center gap-2 px-2 pb-1 border-b border-border/50 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
        <div className="w-6 shrink-0">Pos</div>
        <div className="w-4 shrink-0">#</div>
        <div className="flex-1">Status</div>
        <div className="min-w-[120px] text-center">Best Options</div>
      </div>

      <div className="space-y-1.5 sm:space-y-1">
        {positionKeys.map((pos, idx) => {
          const coverage = positions[pos];
          const IconComponent = positionIcons[pos];
          const hasWarning = positionHasWarning(pos);
          const hasUniqueAssignment = assignedPositions.has(pos);
          const noCoverage = coverage.bestRank >= 6;

          // Determine row color
          let rowColorClass = 'bg-green-900/30 border-green-500/30';
          if (noCoverage) {
            rowColorClass = 'bg-red-900/30 border-red-500/30';
          } else if (hasWarning || !hasUniqueAssignment || coverage.bestRank >= 3) {
            rowColorClass = 'bg-orange-900/30 border-orange-500/30';
          }

          return (
            <div
              key={pos}
              className={cn(
                'flex flex-col sm:flex-row sm:items-center gap-2 p-2 rounded-md border',
                rowColorClass
              )}
            >
              {/* Position Icon + Number */}
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center w-6 shrink-0">
                  <IconComponent className="w-4 h-4" />
                </div>
                <span className="text-xs font-bold w-4 shrink-0">{idx + 1}</span>
              </div>

              {/* Status */}
              <div className="flex-1 min-w-0">
                {noCoverage ? (
                  <span className="text-xs text-red-400">No coverage</span>
                ) : coverage.conflicts.length > 0 ? (
                  <div className="flex flex-col gap-0.5">
                    {coverage.conflicts.map((message, i) => {
                      const isPositive = (message.includes('unique') && !message.includes('No unique')) || message.includes('guessed');
                      return (
                        <span
                          key={i}
                          className={cn(
                            'text-xs',
                            isPositive ? 'text-green-400' : 'text-orange-400'
                          )}
                        >
                          {message}
                        </span>
                      );
                    })}
                  </div>
                ) : (
                  <span className="text-xs text-green-400">Good coverage</span>
                )}
              </div>

              {/* Best players with fallbacks */}
              <div className="shrink-0">
                <BestPlayersRow
                  players={coverage.playersWithRanks}
                  assignedPlayerPk={positionAssignments.get(pos)}
                  maxDisplay={3}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});
PositionConflictTable.displayName = 'PositionConflictTable';

// Team Position Coverage Row - renders all 5 position cards with hover for conflict table
interface TeamPositionCoverageRowProps {
  team: TeamType | undefined;
  className?: string;
  /** Team name for modal title */
  teamName?: string;
  /** Show full table instead of compact cards */
  showFullTable?: boolean;
}

export const TeamPositionCoverageRow = memo(({ team, className, teamName, showFullTable = false }: TeamPositionCoverageRowProps) => {
  const [modalOpen, setModalOpen] = useState(false);

  const teamPositionCoverage = useMemo(() => {
    return computeTeamPositionCoverage(team);
  }, [team]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setModalOpen(true);
  }, []);

  const displayName = teamName || team?.name || (team?.captain ? `${team.captain.nickname || team.captain.username}'s Team` : 'Team');

  // If showFullTable is true, render the table directly without hover/modal
  if (showFullTable) {
    return (
      <div className={className}>
        <PositionConflictTable teamPositionCoverage={teamPositionCoverage} />
      </div>
    );
  }

  return (
    <>
      <HoverCard openDelay={200} closeDelay={100}>
        <HoverCardTrigger asChild>
          <div
            className={cn('flex flex-wrap justify-center items-center gap-1.5 overflow-visible cursor-pointer', className)}
            onClick={handleClick}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setModalOpen(true);
              }
            }}
          >
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
        </HoverCardTrigger>
        <HoverCardContent
          className="w-[400px] p-3 hidden md:block"
          side="bottom"
          align="center"
        >
          <PositionConflictTable teamPositionCoverage={teamPositionCoverage} />
        </HoverCardContent>
      </HoverCard>

      {/* Modal for mobile/click interaction */}
      <InfoDialog
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={`${displayName} - Position Coverage`}
        size="lg"
        showClose
      >
        <PositionConflictTable teamPositionCoverage={teamPositionCoverage} />
      </InfoDialog>
    </>
  );
});
TeamPositionCoverageRow.displayName = 'TeamPositionCoverageRow';
