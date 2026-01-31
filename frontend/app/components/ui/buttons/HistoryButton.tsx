import * as React from 'react';
import { History } from 'lucide-react';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from './SecondaryButton';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

export interface HistoryButtonProps
  extends Omit<React.ComponentProps<typeof SecondaryButton>, 'children'> {
  /** Number of events to display in badge */
  eventCount?: number;
  /** Whether there's a new event (shows destructive badge) */
  hasNewEvent?: boolean;
  /** Tooltip text */
  tooltipText?: string;
  /** Custom label (default: "History") */
  label?: string;
}

/**
 * A responsive history button with optional event badge.
 * Shows icon-only on small screens, full text on lg+ screens.
 *
 * @example
 * ```tsx
 * <HistoryButton
 *   eventCount={5}
 *   hasNewEvent={true}
 *   onClick={() => setModalOpen(true)}
 * />
 * ```
 */
const HistoryButton = React.forwardRef<HTMLButtonElement, HistoryButtonProps>(
  (
    {
      eventCount = 0,
      hasNewEvent = false,
      tooltipText = 'View history',
      label = 'History',
      className,
      ...props
    },
    ref
  ) => {
    const button = (
      <SecondaryButton
        ref={ref}
        color="orange"
        className={cn('relative', className)}
        {...props}
      >
        <History className="h-4 w-4 lg:mr-2" />
        <span className="hidden lg:inline">{label}</span>
        {eventCount > 0 && (
          <Badge
            variant={hasNewEvent ? 'destructive' : 'secondary'}
            className="absolute -top-2 -right-2 h-5 min-w-5 rounded-full text-xs"
          >
            {eventCount}
          </Badge>
        )}
      </SecondaryButton>
    );

    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>{tooltipText}</TooltipContent>
      </Tooltip>
    );
  }
);

HistoryButton.displayName = 'HistoryButton';

export { HistoryButton };
