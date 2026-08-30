import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandGlowLift, brandGradient, brandLabelOnGradient, buttonLift, buttonDisabled } from './styles';

export type PrimaryButtonColor = 'green' | 'blue' | 'yellow';

export interface PrimaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Color theme for the button (omit for brand gradient) */
  color?: PrimaryButtonColor;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
}

const colorClasses: Record<PrimaryButtonColor, string> = {
  green: 'bg-green-700 hover:bg-green-600 text-white shadow-green-900/50',
  blue: 'bg-blue-700 hover:bg-blue-600 text-white shadow-blue-900/50',
  yellow: 'bg-yellow-600 hover:bg-yellow-500 text-black shadow-yellow-900/50',
};

// Two-layer dark text-shadow under every PrimaryButton label: a hard 1px
// stroke that gives the glyph edges definition, plus a soft 3px blurred
// halo that lifts the text off the colored fill so it reads as "set into"
// the button rather than printed on top. Applied to every variant.
const primaryTextStroke =
  '[text-shadow:_0_1px_0_rgba(0,0,0,0.85),_0_2px_3px_rgba(0,0,0,0.5)]';

const brandExtras = `${brandGlowLift} ${brandLabelOnGradient}`;

const PrimaryButton = React.forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ color, className, children, depth = true, ...props }, ref) => {
    const isBrand = !color;
    return (
      <Button
        ref={ref}
        className={cn(
          depth && buttonLift,
          depth && buttonDisabled,
          !depth && 'shadow-lg shadow-black/30',
          isBrand ? [brandGradient, brandExtras] : [colorClasses[color], primaryTextStroke],
          className
        )}
        {...props}
      >
        {children}
      </Button>
    );
  }
);

PrimaryButton.displayName = 'PrimaryButton';

export { PrimaryButton };
