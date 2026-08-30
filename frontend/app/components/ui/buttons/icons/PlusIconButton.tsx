import { PlusCircle } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { LazyTooltip } from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { brandGlowLift, brandGradient, buttonLift } from '../styles';

export interface PlusIconButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Optional tooltip text */
  tooltip?: string;
}

/**
 * A plus/add icon button with brand gradient styling.
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
          buttonLift,
          brandGlowLift,
          '[&_svg]:text-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]',
          className
        )}
        {...props}
      >
        <PlusCircle className="h-4 w-4" />
        <span className="sr-only">{tooltip || 'Add'}</span>
      </Button>
    );

    if (tooltip) {
      return <LazyTooltip content={tooltip}>{button}</LazyTooltip>;
    }

    return button;
  }
);

PlusIconButton.displayName = 'PlusIconButton';

export { PlusIconButton };
