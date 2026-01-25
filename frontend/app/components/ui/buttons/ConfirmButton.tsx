import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export type ConfirmButtonVariant = 'default' | 'destructive' | 'warning' | 'success';

export interface ConfirmButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Visual variant */
  variant?: ConfirmButtonVariant;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

/**
 * A confirm action button with 3D depth effects for use in dialogs.
 * Supports multiple variants for different action types.
 *
 * @example
 * ```tsx
 * // Default confirm
 * <ConfirmButton onClick={handleConfirm}>Confirm</ConfirmButton>
 *
 * // Destructive (delete actions)
 * <ConfirmButton variant="destructive" loading={isDeleting}>
 *   Delete
 * </ConfirmButton>
 *
 * // Warning (restart, undo actions)
 * <ConfirmButton variant="warning" onClick={handleRestart}>
 *   Restart Draft
 * </ConfirmButton>
 *
 * // Success (approve, accept actions)
 * <ConfirmButton variant="success" onClick={handleApprove}>
 *   Approve
 * </ConfirmButton>
 * ```
 */
const ConfirmButton = React.forwardRef<HTMLButtonElement, ConfirmButtonProps>(
  (
    {
      loading = false,
      disabled,
      children,
      className,
      variant = 'default',
      depth = true,
      ...props
    },
    ref
  ) => {
    const variantStyles = {
      default: depth ? button3DVariants.primary : 'bg-primary text-primary-foreground hover:bg-primary/90',
      destructive: depth ? button3DVariants.destructive : 'bg-red-600 text-white hover:bg-red-500',
      warning: depth ? button3DVariants.warning : 'bg-orange-500 text-white hover:bg-orange-400',
      success: depth ? button3DVariants.success : 'bg-green-600 text-white hover:bg-green-500',
    };

    const loadingText = {
      default: 'Confirming...',
      destructive: 'Deleting...',
      warning: 'Processing...',
      success: 'Saving...',
    };

    return (
      <Button
        ref={ref}
        disabled={disabled || loading}
        className={cn(variantStyles[variant], className)}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            {loadingText[variant]}
          </>
        ) : (
          children
        )}
      </Button>
    );
  }
);

ConfirmButton.displayName = 'ConfirmButton';

export { ConfirmButton };
