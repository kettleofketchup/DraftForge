import { Eye } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { brandSecondary } from '../styles';

export interface ViewIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
}

/**
 * A view icon button with brand secondary styling and circular shape.
 * Optionally displays a tooltip on hover.
 *
 * @example
 * ```tsx
 * <ViewIconButton onClick={handleView} tooltip="View details" />
 * ```
 */
const ViewIconButton = React.forwardRef<HTMLButtonElement, ViewIconButtonProps>(
  ({ tooltip, className, ...props }, ref) => {
    const button = (
      <Button
        ref={ref}
        size="icon"
        className={cn(
          'rounded-full',
          brandSecondary,
          'shadow-sm',
          'active:translate-y-0.5 transition-all duration-75',
          '[&_svg]:text-violet-200',
          className
        )}
        {...props}
      >
        <Eye className="h-4 w-4" />
        <span className="sr-only">{tooltip || 'View'}</span>
      </Button>
    );

    if (tooltip) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
      );
    }

    return button;
  }
);

ViewIconButton.displayName = 'ViewIconButton';

export { ViewIconButton };
