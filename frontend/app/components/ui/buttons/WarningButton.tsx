import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandButtonVariants } from './styles';

export interface WarningButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
}

/**
 * A warning button with orange theme styling and a soft-shadow lift.
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
  ({ loading = false, disabled, children, className, depth = true, size, ...props }, ref) => {
    // min-h-11 is the 44px touch target for dialog footers, but it would override
    // an explicit size="sm"/"icon" and leave this button taller than the
    // Primary/Secondary siblings it sits beside in compact action rows.
    const touchTarget = size === 'sm' || size === 'icon' ? undefined : 'min-h-11';
    return (
      <Button
        ref={ref}
        disabled={disabled || loading}
        size={size}
        className={cn(
          touchTarget,
          depth ? brandButtonVariants.warning : 'bg-orange-500 text-white hover:bg-orange-400',
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
