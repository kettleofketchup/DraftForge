import { PlusCircle } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

export interface PlusIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
}

/**
 * A plus/add icon button with green theme styling.
 * Optionally displays a tooltip on hover.
 *
 * @example
 * ```tsx
 * <PlusIconButton onClick={handleAdd} tooltip="Add new item" />
 * ```
 */
const PlusIconButton = React.forwardRef<HTMLButtonElement, PlusIconButtonProps>(
  ({ tooltip, className, ...props }, ref) => {
    const button = (
      <Button
        ref={ref}
        size="icon"
        className={cn(
          'rounded-full',
          'bg-emerald-600 hover:bg-emerald-500 text-white',
          'shadow-lg shadow-emerald-900/50 border-b-4 border-b-emerald-800',
          'active:border-b-0 active:translate-y-1 transition-all duration-75',
          '[&_svg]:text-white',
          className
        )}
        {...props}
      >
        <PlusCircle className="h-4 w-4" />
        <span className="sr-only">{tooltip || 'Add'}</span>
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

PlusIconButton.displayName = 'PlusIconButton';

export { PlusIconButton };
