import { Edit2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

export interface EditIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
}

/**
 * An edit icon button with green theme styling.
 * Optionally displays a tooltip on hover.
 *
 * @example
 * ```tsx
 * <EditIconButton onClick={handleEdit} tooltip="Edit item" />
 * ```
 */
const EditIconButton = React.forwardRef<HTMLButtonElement, EditIconButtonProps>(
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
        <Edit2 className="h-4 w-4" />
        <span className="sr-only">{tooltip || 'Edit'}</span>
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

EditIconButton.displayName = 'EditIconButton';

export { EditIconButton };
