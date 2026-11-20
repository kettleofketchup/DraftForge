import { Badge } from '~/components/ui/badge';

export type RosterStatus = 'standin' | 'dropout' | 'deputy';

const BADGES: Record<
  RosterStatus,
  { label: string; variant: 'secondary' | 'outline'; className?: string }
> = {
  standin: { label: 'Stand-in', variant: 'secondary' },
  dropout: {
    label: 'Dropout',
    variant: 'outline',
    className: 'text-muted-foreground',
  },
  deputy: { label: 'Deputy', variant: 'outline' },
};

export function RosterStatusBadge({ status }: { status: RosterStatus }) {
  const { label, variant, className } = BADGES[status];
  return (
    <Badge
      variant={variant}
      className={className}
      data-testid={`roster-status-${status}`}
    >
      {label}
    </Badge>
  );
}
