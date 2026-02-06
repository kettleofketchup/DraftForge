import { PlusCircle } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { brandGradient, button3DBase } from '../styles';

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
          brandGradient,
          button3DBase,
          'border-b-violet-700 shadow-violet-900/50',
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
