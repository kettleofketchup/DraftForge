import { Edit2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { brandDepthColors, brandGradient, button3DBase } from '../styles';

export interface EditIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
  /** Test ID for Playwright/testing */
  'data-testid'?: string;
}

/**
 * An edit icon button with brand gradient styling.
 * Optionally displays a tooltip on hover.
 *
 * @example
 * ```tsx
 * <EditIconButton onClick={handleEdit} tooltip="Edit item" />
 * ```
 */
const EditIconButton = React.forwardRef<HTMLButtonElement, EditIconButtonProps>(
  ({ tooltip, className, 'data-testid': dataTestId, ...props }, ref) => {
    const button = (
      <Button
        ref={ref}
        size="icon"
        data-testid={dataTestId}
        className={cn(
          'rounded-full',
          brandGradient,
          button3DBase,
          brandDepthColors,
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
