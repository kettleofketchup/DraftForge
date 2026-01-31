import { memo } from 'react';
import { type NodeProps, Position } from '@xyflow/react';
import { BaseNode, BaseNodeContent } from '~/components/ui/base-node';
import { BaseHandle } from '~/components/ui/base-handle';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { EmptySlotData } from '../types';

export const EmptySlotNode = memo(({ data }: NodeProps & { data: EmptySlotData }) => {
  const isStaff = useUserStore((state) => state.isStaff());

  return (
    <BaseNode
      className={cn(
        'w-52 border-dashed border-white/50',
        isStaff && 'cursor-pointer hover:border-white/80'
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
