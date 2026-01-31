import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export interface WarningButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

/**
 * A warning button with orange theme styling and 3D depth effects.
 * Used for caution-level actions that aren't destructive.
 *
 * @example
 * ```tsx
 * <WarningButton onClick={handleWarningAction} loading={isProcessing}>
 *   Proceed with Caution
 * </WarningButton>
 * ```
 */
const WarningButton = React.forwardRef<HTMLButtonElement, WarningButtonProps>(
  ({ loading = false, disabled, children, className, depth = true, ...props }, ref) => {
    return (
      <Button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          depth ? button3DVariants.warning : 'bg-orange-500 text-white hover:bg-orange-400',
          className
        )}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          children
        )}
      </Button>
    );
  }
);

WarningButton.displayName = 'WarningButton';

export { WarningButton };
