import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandGradient, button3DBase, button3DDisabled } from './styles';

export type PrimaryButtonColor = 'green' | 'blue' | 'yellow';

export interface PrimaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Color theme for the button (omit for brand gradient) */
  color?: PrimaryButtonColor;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

const colorClasses: Record<PrimaryButtonColor, string> = {
  green: 'bg-green-700 hover:bg-green-600 text-white border-b-green-900 shadow-green-900/50',
  blue: 'bg-blue-700 hover:bg-blue-600 text-white border-b-blue-900 shadow-blue-900/50',
  yellow: 'bg-yellow-600 hover:bg-yellow-500 text-black border-b-yellow-800 shadow-yellow-900/50',
};

const brandExtras = 'border-b-violet-700 shadow-violet-900/50 [&_svg]:text-white [&_svg]:fill-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';

const PrimaryButton = React.forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ color, className, children, depth = true, ...props }, ref) => {
    const isBrand = !color;
    return (
      <Button
        ref={ref}
        className={cn(
          depth && button3DBase,
          depth && button3DDisabled,
          isBrand ? [brandGradient, brandExtras] : colorClasses[color],
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
