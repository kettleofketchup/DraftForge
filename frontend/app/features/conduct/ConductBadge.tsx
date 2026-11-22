import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import { formatShowRate } from './format';
import type { ForecastMember, Tier } from './schemas';

const TIER_BADGES: Partial<Record<Tier, { label: string; className: string }>> =
  {
    require_approval: {
      label: 'Needs approval',
      className: 'border-warning/30 bg-warning/20 text-warning',
    },
    block: {
      label: 'Blocked',
      className: 'border-destructive/30 bg-destructive/20 text-destructive',
    },
  };

export function ConductBadge({
  member,
  className,
}: {
  member: ForecastMember | undefined;
  className?: string;
}) {
  if (!member) return null;
  const tierBadge = TIER_BADGES[member.tier];
  const rate = formatShowRate(member);

  return (
    <span
      className={cn(
        'inline-flex flex-wrap items-center justify-end gap-1',
        className,
      )}
    >
      <Badge
        variant="outline"
        className="border-border bg-muted text-muted-foreground"
        data-testid="conduct-badge"
        title="Show rate"
      >
        Show<span className="sr-only"> rate</span> {rate}
      </Badge>
      {tierBadge && (
        <Badge
          variant="outline"
          className={tierBadge.className}
          data-testid="conduct-badge-tier"
        >
          {tierBadge.label}
        </Badge>
      )}
    </span>
  );
}
