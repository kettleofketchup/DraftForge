import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import { brandSecondary, brandSecondaryLift, buttonLift, buttonDisabled } from './styles';

export type SecondaryColor = 'green' | 'blue' | 'purple' | 'orange' | 'red' | 'sky' | 'cyan' | 'lime' | 'emerald';

export interface SecondaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Optional background color for contextual actions */
  color?: SecondaryColor;
  /** Whether to apply the soft-shadow lift (default: false for brand, true for colored) */
  depth?: boolean;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

const colorStyles: Record<SecondaryColor, string> = {
  green: `${buttonLift} ${buttonDisabled} bg-green-800 hover:bg-green-700 text-white shadow-green-900/50`,
  blue: `${buttonLift} ${buttonDisabled} bg-blue-800 hover:bg-blue-700 text-white shadow-blue-900/50`,
  purple: `${buttonLift} ${buttonDisabled} bg-purple-800 hover:bg-purple-700 text-white shadow-purple-900/50`,
  orange: `${buttonLift} ${buttonDisabled} bg-orange-800 hover:bg-orange-700 text-white shadow-orange-900/50`,
  red: `${buttonLift} ${buttonDisabled} bg-red-800 hover:bg-red-700 text-white shadow-red-900/50`,
  sky: `${buttonLift} ${buttonDisabled} bg-sky-800 hover:bg-sky-700 text-white shadow-sky-900/50`,
  cyan: `${buttonLift} ${buttonDisabled} bg-cyan-700 hover:bg-cyan-600 text-white shadow-cyan-900/50`,
  lime: `${buttonLift} ${buttonDisabled} bg-lime-700 hover:bg-lime-600 text-white shadow-lime-900/50`,
  emerald: `${buttonLift} ${buttonDisabled} bg-emerald-800 hover:bg-emerald-700 text-white shadow-emerald-900/50`,
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
 * // With soft-shadow lift
 * <SecondaryButton depth>Secondary with Depth</SecondaryButton>
 *
 * // Colored variant for contextual actions
 * <SecondaryButton color="sky" size="sm">Regenerate</SecondaryButton>
 * ```
 */
const SecondaryButton = React.forwardRef<
  HTMLButtonElement,
  SecondaryButtonProps
>(({ color, className, children, depth, hotkey, ...props }, ref) => {
  const useDepth = depth ?? !!color;
  const styles = color
    ? colorStyles[color]
    : useDepth
      ? brandSecondaryLift
      : brandSecondary;

  // When hotkey is unset we must pass `children` as the single child so this
  // button stays compatible with `asChild` callers (e.g. <DotabuffButton>).
  // JSX `{a}{b}` always produces a children array even when one branch is
  // falsy, which trips Radix Slot's React.Children.only check.
  return (
    <Button
      ref={ref}
      // No variant prop — brand styles fully control appearance via className.
      // Passing variant="secondary" introduces shadcn classes that override brand bg.
      className={cn(
        styles,
        !useDepth && 'shadow-lg shadow-black/30',
        hotkey && 'relative',
        className,
      )}
      {...props}
    >
      {hotkey ? (
        <>
          <HotkeyBadge hotkey={hotkey} />
          {children}
        </>
      ) : (
        children
      )}
    </Button>
  );
});

SecondaryButton.displayName = 'SecondaryButton';

export { SecondaryButton };
