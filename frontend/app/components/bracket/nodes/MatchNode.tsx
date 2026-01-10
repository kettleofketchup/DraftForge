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
import type { MatchNodeData } from '../types';
import type { TeamType } from '~/components/tournament/types';
import { getRoundLabel } from '../utils/doubleElimination';
import { BracketBadge } from '../BracketBadge';
import { getBadgeLetter } from '../utils/badgeUtils';

const statusConfig = {
  pending: { label: 'Upcoming', className: 'bg-muted text-muted-foreground' },
  live: { label: 'LIVE', className: 'bg-red-500 text-white animate-pulse' },
  completed: { label: 'Final', className: 'bg-green-500/20 text-green-500' },
};

// Bracket type visual styling
const bracketTypeStyles = {
  winners: {
    bg: 'bg-background',
    border: 'border-border',
    headerBg: '',
  },
  losers: {
    bg: 'bg-red-950/30',
    border: 'border-red-800/60',
    headerBg: 'bg-red-900/30',
  },
  grand_finals: {
    bg: 'bg-purple-950/20',
    border: 'border-purple-700/50',
    headerBg: 'bg-purple-900/20',
  },
  swiss: {
    bg: 'bg-blue-950/20',
    border: 'border-blue-700/50',
    headerBg: 'bg-blue-900/20',
  },
};

export const MatchNode = memo(({ data, selected }: NodeProps & { data: MatchNodeData }) => {
  const status = statusConfig[data.status];
  const roundLabel = getRoundLabel(data.bracketType, data.round);
  const bracketStyle = bracketTypeStyles[data.bracketType] || bracketTypeStyles.winners;

  // Calculate badge for winners bracket
  const winnersBadgeLetter =
    data.bracketType === 'winners' && data.loserNextMatchId
      ? getBadgeLetter(data.bracketType, data.round, data.position, true)
      : null;

  // Get badges for losers bracket slots
  const radiantBadgeLetter = data.badgeMapping?.[`${data.id}:radiant`];
  const direBadgeLetter = data.badgeMapping?.[`${data.id}:dire`];

  return (
    <BaseNode
      className={cn(
        'w-52 cursor-pointer transition-all relative',
        bracketStyle.bg,
        bracketStyle.border,
        selected && 'ring-2 ring-primary'
      )}
    >
      {/* Left handle - receives winner from previous match */}
      <BaseHandle type="target" position={Position.Left} />

      {/* Losers bracket badges - left side of slots */}
      {data.bracketType === 'losers' && radiantBadgeLetter && (
        <BracketBadge letter={radiantBadgeLetter} position="left" slot="top" />
      )}
      {data.bracketType === 'losers' && direBadgeLetter && (
        <BracketBadge letter={direBadgeLetter} position="left" slot="bottom" />
      )}

      {/* Header with round label and status */}
      <BaseNodeHeader className={cn('border-b pb-2', bracketStyle.headerBg)}>
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

      {/* Winners bracket badge - right side */}
      {winnersBadgeLetter && (
        <BracketBadge letter={winnersBadgeLetter} position="right" />
      )}
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

  // Use captain's username and avatar
  const captain = team.captain;
  const displayName = captain?.username ?? team.name ?? 'Unknown';
  const avatarUrl = captain?.avatarUrl ?? captain?.avatar;

  return (
    <div
      className={cn(
        'flex items-center gap-2 p-1.5 rounded transition-colors',
        isWinner && isCompleted && 'bg-green-500/10',
        !isWinner && isCompleted && 'opacity-50'
      )}
    >
      {/* Captain avatar */}
      <Avatar className="h-6 w-6">
        <AvatarImage src={avatarUrl ?? undefined} />
        <AvatarFallback className="text-xs">
          {displayName.substring(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>

      {/* Captain username */}
      <span
        className={cn(
          'flex-1 text-sm truncate max-w-[120px]',
          isWinner && isCompleted && 'font-semibold'
        )}
        title={displayName}
      >
        {displayName}
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
      {isWinner && isCompleted && <span className="text-green-500">&#x2713;</span>}
    </div>
  );
}
