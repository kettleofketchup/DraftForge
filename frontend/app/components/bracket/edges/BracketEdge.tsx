import { memo } from 'react';
import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react';

interface BracketEdgeData {
  isWinnerPath?: boolean;
  isLoserPath?: boolean;
}

export const BracketEdge = memo(
  ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    style,
  }: EdgeProps<BracketEdgeData>) => {
    const [edgePath] = getSmoothStepPath({
      sourceX,
      sourceY,
      targetX,
      targetY,
      sourcePosition,
      targetPosition,
      borderRadius: 8,
    });

    return (
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          strokeWidth: data?.isWinnerPath ? 3 : 2,
          stroke: data?.isWinnerPath
            ? 'rgb(34 197 94)' // green-500
            : data?.isLoserPath
              ? 'rgb(239 68 68)' // red-500
              : 'rgb(148 163 184)', // slate-400
        }}
      />
    );
  }
);

BracketEdge.displayName = 'BracketEdge';
