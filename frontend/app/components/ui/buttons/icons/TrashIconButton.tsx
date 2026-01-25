import { Trash2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';

export type IconButtonSize = 'sm' | 'default';

export interface TrashIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
  /** Button size */
  size?: IconButtonSize;
}

const sizeClasses: Record<IconButtonSize, { button: string; icon: string }> = {
  sm: { button: 'h-8 w-8', icon: 'h-3 w-3' },
  default: { button: 'h-9 w-9', icon: 'h-4 w-4' },
};

/**
 * A trash/delete icon button with destructive styling.
 * Optionally displays a tooltip on hover.
 *
 * @example
 * ```tsx
 * <TrashIconButton onClick={handleDelete} tooltip="Delete item" />
 * <TrashIconButton size="sm" onClick={handleRemove} />
 * ```
 */
const TrashIconButton = React.forwardRef<
  HTMLButtonElement,
  TrashIconButtonProps
>(({ tooltip, size = 'default', className, ...props }, ref) => {
  const sizeConfig = sizeClasses[size];

  const button = (
    <Button
      ref={ref}
      variant="destructive"
      size="icon"
      className={cn(
        'rounded-full',
        'shadow-lg shadow-red-900/50 border-b-4 border-b-red-800',
        'active:border-b-0 active:translate-y-1 transition-all duration-75',
        sizeConfig.button,
        className
      )}
      {...props}
    >
      <Trash2 className={sizeConfig.icon} />
      <span className="sr-only">{tooltip || 'Delete'}</span>
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
});

TrashIconButton.displayName = 'TrashIconButton';

export { TrashIconButton };
