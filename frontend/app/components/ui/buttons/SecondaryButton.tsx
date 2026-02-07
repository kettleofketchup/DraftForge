import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandSecondary, brandSecondary3D, button3DBase, button3DDisabled } from './styles';

export type SecondaryColor = 'green' | 'blue' | 'purple' | 'orange' | 'red' | 'sky' | 'cyan' | 'lime';

export interface SecondaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Optional background color for contextual actions */
  color?: SecondaryColor;
  /** Whether to apply 3D depth effects (default: false for brand, true for colored) */
  depth?: boolean;
}

const colorStyles: Record<SecondaryColor, string> = {
  green: `${button3DBase} ${button3DDisabled} bg-green-800 hover:bg-green-700 text-white border-b-green-950 shadow-green-900/50`,
  blue: `${button3DBase} ${button3DDisabled} bg-blue-800 hover:bg-blue-700 text-white border-b-blue-950 shadow-blue-900/50`,
  purple: `${button3DBase} ${button3DDisabled} bg-purple-800 hover:bg-purple-700 text-white border-b-purple-950 shadow-purple-900/50`,
  orange: `${button3DBase} ${button3DDisabled} bg-orange-800 hover:bg-orange-700 text-white border-b-orange-950 shadow-orange-900/50`,
  red: `${button3DBase} ${button3DDisabled} bg-red-800 hover:bg-red-700 text-white border-b-red-950 shadow-red-900/50`,
  sky: `${button3DBase} ${button3DDisabled} bg-sky-800 hover:bg-sky-700 text-white border-b-sky-950 shadow-sky-900/50`,
  cyan: `${button3DBase} ${button3DDisabled} bg-cyan-700 hover:bg-cyan-600 text-white border-b-cyan-900 shadow-cyan-900/50`,
  lime: `${button3DBase} ${button3DDisabled} bg-lime-700 hover:bg-lime-600 text-white border-b-lime-900 shadow-lime-900/50`,
};

/**
 * A secondary action button with brand violet styling by default.
 * Default is translucent violet tint (same as the Stats button in team drafts).
 * Pass `color` for contextual colored variants.
 *
 * @example
 * ```tsx
 * // Brand secondary (default) - translucent violet tint
 * <SecondaryButton onClick={handleAction}>Stats</SecondaryButton>
 *
 * // With 3D depth
 * <SecondaryButton depth>Secondary with Depth</SecondaryButton>
 *
 * // Colored variant for contextual actions
 * <SecondaryButton color="sky" size="sm">Regenerate</SecondaryButton>
 * ```
 */
const SecondaryButton = React.forwardRef<
  HTMLButtonElement,
  SecondaryButtonProps
>(({ color, className, children, depth, ...props }, ref) => {
  const useDepth = depth ?? !!color;
  const styles = color
    ? colorStyles[color]
    : useDepth
      ? brandSecondary3D
      : brandSecondary;

  return (
    <Button
      ref={ref}
      // No variant prop — brand styles fully control appearance via className.
      // Passing variant="secondary" introduces shadcn classes that override brand bg.
      className={cn(styles, !useDepth && 'shadow-lg shadow-black/30', className)}
      {...props}
    >
      {children}
    </Button>
  );
});

SecondaryButton.displayName = 'SecondaryButton';

export { SecondaryButton };
