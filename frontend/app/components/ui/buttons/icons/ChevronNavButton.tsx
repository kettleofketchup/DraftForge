import { ChevronsLeft, ChevronsRight } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandDepthColors, brandGradient, button3DBase } from '../styles';

export type ChevronDirection = 'left' | 'right';

export interface ChevronNavButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'size'> {
  /** Direction of the chevron icon */
  direction: ChevronDirection;
}

const directionConfig: Record<
  ChevronDirection,
  { icon: React.ComponentType<{ className?: string }>; label: string }
> = {
  left: { icon: ChevronsLeft, label: 'Navigate left' },
  right: { icon: ChevronsRight, label: 'Navigate right' },
};

/**
 * A chevron navigation icon button with sky blue theme styling.
 * Used for navigation between items or pages.
 *
 * @example
 * ```tsx
 * <ChevronNavButton direction="left" onClick={goBack} />
 * <ChevronNavButton direction="right" onClick={goForward} />
 * ```
 */
const ChevronNavButton = React.forwardRef<
  HTMLButtonElement,
  ChevronNavButtonProps
>(({ direction, className, ...props }, ref) => {
  const config = directionConfig[direction];
  const Icon = config.icon;

  return (
    <Button
      ref={ref}
      size="icon"
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
      <Icon className="h-4 w-4" />
      <span className="sr-only">{config.label}</span>
    </Button>
  );
});

ChevronNavButton.displayName = 'ChevronNavButton';

export { ChevronNavButton };
