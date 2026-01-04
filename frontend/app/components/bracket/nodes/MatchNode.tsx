import { memo } from 'react';
import { type NodeProps, Position, type Node } from '@xyflow/react';
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

const statusConfig = {
  pending: { label: 'Upcoming', className: 'bg-muted text-muted-foreground' },
  live: { label: 'LIVE', className: 'bg-red-500 text-white animate-pulse' },
  completed: { label: 'Final', className: 'bg-green-500/20 text-green-500' },
};

// Node type for match nodes in the bracket
type MatchNodeType = Node<MatchNodeData, 'match'>;

export const MatchNode = memo(({ data, selected }: NodeProps<MatchNodeType>) => {
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

  // Get avatar URL from captain - supports both avatarUrl and avatar fields
  const avatarUrl = team.captain?.avatarUrl ?? team.captain?.avatar;
  const teamName = team.name ?? 'Unknown Team';

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
        <AvatarImage src={avatarUrl ?? undefined} />
        <AvatarFallback className="text-xs">
          {teamName.substring(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>

      {/* Team name */}
      <span
        className={cn(
          'flex-1 text-sm truncate',
          isWinner && isCompleted && 'font-semibold'
        )}
      >
        {teamName}
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
