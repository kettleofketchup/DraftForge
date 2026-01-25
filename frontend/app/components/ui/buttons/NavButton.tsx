import { ChevronLeft, ChevronRight, ChevronsRight } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export type NavDirection = 'prev' | 'next' | 'latest';

export interface NavButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Navigation direction - determines icon and default text */
  direction?: NavDirection;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

const directionConfig: Record<
  NavDirection,
  { icon: React.ComponentType<{ className?: string }>; label: string; iconPosition: 'left' | 'right' }
> = {
  prev: { icon: ChevronLeft, label: 'Previous', iconPosition: 'left' },
  next: { icon: ChevronRight, label: 'Next', iconPosition: 'right' },
  latest: { icon: ChevronsRight, label: 'Latest', iconPosition: 'right' },
};

/**
 * A navigation button with sky blue theme styling and 3D depth effects.
 * Used for navigation between pages or items.
 *
 * @example
 * ```tsx
 * <NavButton direction="prev" onClick={goToPrevious} />
 * <NavButton direction="next" onClick={goToNext} />
 * <NavButton direction="latest" onClick={goToLatest}>Jump to Latest</NavButton>
 * ```
 */
const NavButton = React.forwardRef<HTMLButtonElement, NavButtonProps>(
  ({ direction, children, className, depth = true, ...props }, ref) => {
    const config = direction ? directionConfig[direction] : null;
    const Icon = config?.icon;

    return (
      <Button
        ref={ref}
        className={cn(
          depth ? button3DVariants.nav : 'bg-sky-700 text-white hover:bg-sky-600',
          className
        )}
        {...props}
      >
        {config && Icon && config.iconPosition === 'left' && (
          <Icon className="h-4 w-4 mr-1" />
        )}
        {children || config?.label}
        {config && Icon && config.iconPosition === 'right' && (
          <Icon className="h-4 w-4 ml-1" />
        )}
      </Button>
    );
  }
);

NavButton.displayName = 'NavButton';

export { NavButton };
