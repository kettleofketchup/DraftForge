import { Badge } from '~/components/ui/badge';
import { cn } from '~/lib/utils';
import { EventState, SignupStatus } from './schemas';

const stateConfig: Record<string, { label: string; className: string }> = {
  // Event states
  [EventState.UPCOMING]: { label: 'Upcoming', className: 'bg-info/20 text-info border-info/30' },
  [EventState.SIGNUPS_OPEN]: { label: 'Signups Open', className: 'bg-success/20 text-success border-success/30' },
  [EventState.ROLL_CALL]: { label: 'Roll Call', className: 'bg-warning/20 text-warning border-warning/30' },
  [EventState.IN_PROGRESS]: { label: 'In Progress', className: 'bg-primary/20 text-primary border-primary/30' },
  [EventState.COMPLETED]: { label: 'Completed', className: 'bg-muted text-muted-foreground border-border' },
  [EventState.CANCELLED]: { label: 'Cancelled', className: 'bg-error/20 text-error border-error/30' },
  // Signup statuses
  [SignupStatus.RSVP]: { label: 'RSVP', className: 'bg-info/20 text-info border-info/30' },
  [SignupStatus.PENDING_APPROVAL]: { label: 'Pending', className: 'bg-warning/20 text-warning border-warning/30' },
  [SignupStatus.APPROVED]: { label: 'Approved', className: 'bg-primary/20 text-primary border-primary/30' },
  [SignupStatus.CONFIRMED]: { label: 'Confirmed', className: 'bg-success/20 text-success border-success/30' },
  [SignupStatus.WAITLISTED]: { label: 'Waitlisted', className: 'bg-muted text-muted-foreground border-border' },
  [SignupStatus.REJECTED]: { label: 'Rejected', className: 'bg-error/20 text-error border-error/30' },
};

export function EventStateBadge({ state, className }: { state: string; className?: string }) {
  const config = stateConfig[state] ?? { label: state, className: '' };
  return (
    <Badge variant="outline" className={cn(config.className, className)}>
      {config.label}
    </Badge>
  );
}
