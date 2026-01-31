import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';

export type PrimaryButtonColor = 'green' | 'blue' | 'yellow';

export interface PrimaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Color theme for the button */
  color?: PrimaryButtonColor;
}

const colorClasses: Record<PrimaryButtonColor, string> = {
  green: 'bg-green-700 hover:bg-green-600 text-white',
  blue: 'bg-blue-700 hover:bg-blue-600 text-white',
  yellow: 'bg-yellow-600 hover:bg-yellow-500 text-black',
};

/**
 * A primary action button with customizable color themes.
 * Uses default variant styling with optional color overrides.
 *
 * @example
 * ```tsx
 * <PrimaryButton color="green" onClick={handleSave}>
 *   Save
 * </PrimaryButton>
 *
 * <PrimaryButton color="blue" size="lg">
 *   Continue
 * </PrimaryButton>
 * ```
 */
const PrimaryButton = React.forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ color, className, children, ...props }, ref) => {
    return (
      <Button
        ref={ref}
        className={cn(color && colorClasses[color], className)}
        {...props}
      >
        {children}
      </Button>
    );
  }
);

PrimaryButton.displayName = 'PrimaryButton';

export { PrimaryButton };
