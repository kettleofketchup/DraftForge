import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';

export type RosterStatus = 'captain' | 'deputy' | 'standin' | 'dropout';

export const ROSTER_BADGE_SIZE = 'px-1.5 py-0 text-[10px] leading-4';

const BADGES: Record<RosterStatus, { label: string; tone: string }> = {
  captain: {
    label: 'Captain',
    tone: 'bg-primary text-primary-foreground border-primary',
  },
  deputy: { label: 'Deputy', tone: 'text-primary border-primary/30' },
  standin: { label: 'Stand-in', tone: 'bg-info/15 text-info border-info/30' },
  dropout: { label: 'Dropout', tone: 'text-muted-foreground border-border' },
};

export function RosterStatusBadge({ status }: { status: RosterStatus }) {
  const { label, tone } = BADGES[status];
  return (
    <Badge
      variant="outline"
      className={cn(ROSTER_BADGE_SIZE, tone)}
      data-testid={`roster-status-${status}`}
    >
      {label}
    </Badge>
  );
}
