import { Badge } from '~/components/ui/badge';
import { LazyTooltip } from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { DEFERRED_NOTE, type ForecastMember } from './schemas';
import { scoreLabel } from './scoring';

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
        {scoreLabel(member)}
      </Badge>
      {member.deferred && (
        <LazyTooltip content={DEFERRED_NOTE}>
          <Badge
            variant="outline"
            role="note"
            tabIndex={0}
            aria-label={DEFERRED_NOTE}
            className="border-warning/30 bg-warning/20 text-warning"
            data-testid="conduct-badge-deferred"
          >
            Deferred
          </Badge>
        </LazyTooltip>
      )}
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
