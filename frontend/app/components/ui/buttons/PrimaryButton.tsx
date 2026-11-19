import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import {
  brandGlowLift,
  brandGradient,
  brandLabelOnGradient,
  buttonDisabled,
  buttonLift,
} from './styles';

export type PrimaryButtonColor = 'green' | 'blue' | 'yellow';

export interface PrimaryButtonProps extends Omit<
  React.ComponentProps<typeof Button>,
  'variant'
> {
  /** Color theme for the button (omit for brand gradient) */
  color?: PrimaryButtonColor;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
}

const colorClasses: Record<PrimaryButtonColor, string> = {
  green: 'bg-success/60 hover:bg-success/80 text-white shadow-success/20',
  blue: 'bg-accent hover:brightness-110 text-white shadow-accent/30',
  yellow: 'bg-warning/80 hover:bg-warning/95 text-black shadow-warning/20',
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
          isBrand
            ? [brandGradient, brandExtras]
            : [colorClasses[color], primaryTextStroke],
          className,
        )}
        {...props}
      >
        {children}
      </Button>
    );
  },
);

PrimaryButton.displayName = 'PrimaryButton';

export { PrimaryButton };
