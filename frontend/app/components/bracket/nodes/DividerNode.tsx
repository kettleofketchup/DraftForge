import { memo } from 'react';
import { type NodeProps } from '@xyflow/react';

export interface DividerNodeData {
  [key: string]: unknown;
  width: number;
  label?: string;
}

/**
 * A horizontal divider line node for separating bracket sections
 * Uses pointer-events: none so it doesn't interfere with other nodes
 */
export const DividerNode = memo(({ data }: NodeProps & { data: DividerNodeData }) => {
  return (
    <div
      className="flex items-center gap-4"
      style={{
        width: data.width,
        pointerEvents: 'none',
        position: 'relative',
        zIndex: -1,
      }}
    >
      {/* Left line */}
      <div className="flex-1 h-[3px] bg-red-600 rounded-full shadow-[0_0_8px_rgba(220,38,38,0.5)]" />

      {/* Label */}
      {data.label && (
        <span className="text-red-500 text-xs font-semibold uppercase tracking-wider whitespace-nowrap px-2 bg-background/80 rounded">
          {data.label}
        </span>
      )}

      {/* Right line */}
      <div className="flex-1 h-[3px] bg-red-600 rounded-full shadow-[0_0_8px_rgba(220,38,38,0.5)]" />
    </div>
  );
});

DividerNode.displayName = 'DividerNode';
