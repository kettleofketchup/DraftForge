import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import { OUTCOME_LABELS, type Outcome } from './schemas';

const OUTCOME_CLASS: Record<Outcome, string> = {
  attended: 'bg-success/20 text-success border-success/30',
  no_show: 'bg-destructive/20 text-destructive border-destructive/30',
  late_cancel: 'bg-warning/20 text-warning border-warning/30',
  excused: 'bg-muted text-muted-foreground border-border',
  pending: 'bg-muted text-muted-foreground border-border',
};

export function OutcomeChip({
  outcome,
  className,
}: {
  outcome: Outcome;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={cn(OUTCOME_CLASS[outcome], className)}
      data-testid={`conduct-outcome-${outcome}`}
    >
      {OUTCOME_LABELS[outcome]}
    </Badge>
  );
}
