import type React from 'react';
import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';

const MIN_STREAK = 3;

export const StreakBadge: React.FC<{
  streak: { result: 'W' | 'L'; count: number } | null;
}> = ({ streak }) => {
  if (!streak || streak.count < MIN_STREAK) return null;
  const win = streak.result === 'W';
  return (
    <Badge
      data-testid="streak-badge"
      className={cn(
        'rounded-[2px] border-transparent px-1 py-px text-[10px] leading-none font-semibold tabular-nums',
        win ? 'bg-success/15 text-success' : 'bg-destructive/25 text-foreground',
      )}
    >
      {streak.result}
      {streak.count}
    </Badge>
  );
};
