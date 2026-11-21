import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import { formatShowRate } from './format';
import type { ForecastMember } from './schemas';

export function ConductBadge({
  member,
  className,
}: {
  member: ForecastMember | undefined;
  className?: string;
}) {
  if (!member) return null;
  const needsApproval =
    member.tier === 'require_approval' || member.tier === 'block';

  return (
    <span className={cn('inline-flex items-center gap-1', className)}>
      <Badge
        variant="outline"
        className="border-border bg-muted text-muted-foreground"
        data-testid="conduct-badge"
      >
        <span className="sr-only">Show rate </span>
        {formatShowRate(member)}
      </Badge>
      {needsApproval && (
        <Badge
          variant="outline"
          className="border-destructive/30 bg-destructive/20 text-destructive"
          data-testid="conduct-badge-approval"
        >
          Needs approval
        </Badge>
      )}
    </span>
  );
}
