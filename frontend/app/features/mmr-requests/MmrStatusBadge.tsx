import { BadgeCheck, Clock } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import { formatMmrDate } from './format';

export interface MmrStatusBadgeProps {
  verified: boolean;
  legacy?: boolean;
  pending?: boolean;
  verifiedBy?: string | null;
  verifiedAt?: string | null;
  className?: string;
}

export function MmrStatusBadge({
  verified,
  legacy = false,
  pending = false,
  verifiedBy,
  verifiedAt,
  className,
}: MmrStatusBadgeProps) {
  const date = formatMmrDate(verifiedAt);
  const verifier = verified && !legacy && verifiedBy ? verifiedBy : null;
  const officialTitle = legacy
    ? 'Verified before review history was kept'
    : verifier
      ? `Verified by ${verifier}${date ? ` on ${date}` : ''}`
      : 'Verified by staff';

  return (
    <span
      className={cn('inline-flex flex-wrap items-center gap-1.5', className)}
    >
      {verified ? (
        <Badge
          className="gap-1 border-transparent bg-success text-success-foreground"
          data-testid="mmr-badge-official"
          title={officialTitle}
        >
          <BadgeCheck className="size-3" aria-hidden />
          Official
        </Badge>
      ) : (
        <Badge
          variant="outline"
          className="border-warning/30 bg-warning/15 text-warning"
          data-testid="mmr-badge-unverified"
          title="Self-reported, not yet checked by staff"
        >
          Unverified
        </Badge>
      )}
      {verifier && (
        <span
          className="text-xs text-muted-foreground"
          data-testid="mmr-badge-verifier"
        >
          by {verifier}
          {date ? ` · ${date}` : ''}
        </span>
      )}
      {pending && (
        <Badge
          className="gap-1 border-transparent bg-warning text-warning-foreground"
          data-testid="mmr-badge-pending"
        >
          <Clock className="size-3" aria-hidden />
          Pending
        </Badge>
      )}
    </span>
  );
}
