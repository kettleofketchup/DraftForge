import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DBase, button3DDisabled } from './styles';

export type BorderColor = 'green' | 'blue' | 'purple' | 'orange' | 'red' | 'sky' | 'cyan' | 'lime';

export interface SecondaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Optional colored border */
  borderColor?: BorderColor;
  /** Optional background color */
  color?: BorderColor;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

const borderColorClasses: Record<BorderColor, string> = {
  green: 'border border-green-600',
  blue: 'border border-blue-600',
  purple: 'border border-purple-600',
  orange: 'border border-orange-600',
  red: 'border border-red-600',
  sky: 'border border-sky-600',
  cyan: 'border border-cyan-600',
  lime: 'border border-lime-500',
};

const bgColorClasses: Record<BorderColor, string> = {
  green: 'bg-green-800 hover:bg-green-700 text-white border-b-green-950 shadow-green-900/50',
  blue: 'bg-blue-800 hover:bg-blue-700 text-white border-b-blue-950 shadow-blue-900/50',
  purple: 'bg-purple-800 hover:bg-purple-700 text-white border-b-purple-950 shadow-purple-900/50',
  orange: 'bg-orange-800 hover:bg-orange-700 text-white border-b-orange-950 shadow-orange-900/50',
  red: 'bg-red-800 hover:bg-red-700 text-white border-b-red-950 shadow-red-900/50',
  sky: 'bg-sky-800 hover:bg-sky-700 text-white border-b-sky-950 shadow-sky-900/50',
  cyan: 'bg-cyan-700 hover:bg-cyan-600 text-white border-b-cyan-900 shadow-cyan-900/50',
  lime: 'bg-lime-700 hover:bg-lime-600 text-white border-b-lime-900 shadow-lime-900/50',
};

/**
 * A secondary action button with optional colored border and 3D depth effects.
 * Uses secondary variant styling with optional border color overrides.
 *
 * @example
 * ```tsx
 * <SecondaryButton onClick={handleAction}>
 *   Secondary Action
 * </SecondaryButton>
 *
 * <SecondaryButton borderColor="green" size="sm">
 *   With Green Border
 * </SecondaryButton>
 *
 * <SecondaryButton color="cyan" depth>
 *   With Cyan Background and 3D Effect
 * </SecondaryButton>
 * ```
 */
const SecondaryButton = React.forwardRef<
  HTMLButtonElement,
  SecondaryButtonProps
>(({ borderColor, color, className, children, depth = true, ...props }, ref) => {
  return (
    <Button
      ref={ref}
      variant="secondary"
      className={cn(
        depth && button3DBase,
        depth && button3DDisabled,
        depth && '[&_svg]:text-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]',
        borderColor && borderColorClasses[borderColor],
        color && bgColorClasses[color],
        className
      )}
      {...props}
    >
      {children}
    </Button>
  );
});

SecondaryButton.displayName = 'SecondaryButton';

export { SecondaryButton };
