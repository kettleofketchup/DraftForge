import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';

import { ROSTER_BADGE_SIZE } from './manage/RosterStatusBadge';
import { type TeamStatus, teamStatus, teamStatusLabel } from './teamStatus';

const TONES: Record<TeamStatus, string> = {
  live: 'text-success border-success/30 bg-success/10',
  winner: 'text-primary border-primary/30 bg-primary/10',
  eliminated: 'text-muted-foreground border-border',
};

export function TeamStatusBadge({
  placement,
  className,
}: {
  placement: number | null | undefined;
  className?: string;
}) {
  const status = teamStatus(placement);
  return (
    <Badge
      variant="outline"
      className={cn(ROSTER_BADGE_SIZE, TONES[status], className)}
      data-testid="team-status-badge"
      data-status={status}
    >
      {teamStatusLabel(placement)}
    </Badge>
  );
}
