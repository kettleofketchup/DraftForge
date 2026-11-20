import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import {
  brandSecondary,
  brandSecondaryLift,
  buttonDisabled,
  buttonLift,
} from './styles';

export type SecondaryColor =
  | 'green'
  | 'blue'
  | 'purple'
  | 'orange'
  | 'red'
  | 'sky'
  | 'cyan'
  | 'emerald';

export interface SecondaryButtonProps extends Omit<
  React.ComponentProps<typeof Button>,
  'variant'
> {
  /** Optional background color for contextual actions */
  color?: SecondaryColor;
  /** Whether to apply the soft-shadow lift (default: false for brand, true for colored) */
  depth?: boolean;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

const colorStyles: Record<SecondaryColor, string> = {
  green: `${buttonLift} ${buttonDisabled} bg-success/45 hover:bg-success/60 text-white shadow-success/20`,
  blue: `${buttonLift} ${buttonDisabled} bg-accent/75 hover:bg-accent/95 text-white shadow-accent/30`,
  purple: `${buttonLift} ${buttonDisabled} bg-selection/65 hover:bg-selection/80 text-white shadow-selection/25`,
  orange: `${buttonLift} ${buttonDisabled} bg-warning/45 hover:bg-warning/60 text-white shadow-warning/20`,
  red: `${buttonLift} ${buttonDisabled} bg-destructive/60 hover:bg-destructive/75 text-white shadow-destructive/25`,
  sky: `${buttonLift} ${buttonDisabled} bg-accent/75 hover:bg-accent/95 text-white shadow-accent/30`,
  cyan: `${buttonLift} ${buttonDisabled} bg-interactive/55 hover:bg-interactive/70 text-white shadow-interactive/15`,
  emerald: `${buttonLift} ${buttonDisabled} bg-success/40 hover:bg-success/55 text-white shadow-success/15`,
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
