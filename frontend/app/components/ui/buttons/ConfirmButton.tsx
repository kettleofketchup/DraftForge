import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import { brandGradient, brandButtonVariants } from './styles';

export type ConfirmButtonVariant = 'default' | 'destructive' | 'warning' | 'success';

export interface ConfirmButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Visual variant */
  variant?: ConfirmButtonVariant;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

/**
 * A confirm action button with a soft-shadow lift for use in dialogs.
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
      hotkey,
      ...props
    },
    ref
  ) => {
    const variantStyles = {
      default: depth ? brandButtonVariants.success : brandGradient,
      destructive: depth ? brandButtonVariants.destructive : 'bg-red-600 text-white hover:bg-red-500',
      warning: depth ? brandButtonVariants.warning : 'bg-orange-500 text-white hover:bg-orange-400',
      success: depth ? brandButtonVariants.success : brandGradient,
    };

    const loadingText = {
      default: 'Confirming...',
      destructive: 'Deleting...',
      warning: 'Processing...',
      success: 'Saving...',
    };

    // When hotkey is unset, pass a single child so `asChild` callers stay
    // valid (Slot's React.Children.only rejects arrays — see SecondaryButton).
    const inner = loading ? (
      <>
        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
        {loadingText[variant]}
      </>
    ) : (
      children
    );

    return (
      <Button
        ref={ref}
        disabled={disabled || loading}
        className={cn('min-h-11', variantStyles[variant], hotkey && 'relative', className)}
        {...props}
      >
        {hotkey ? (
          <>
            <HotkeyBadge hotkey={hotkey} />
            {inner}
          </>
        ) : (
          inner
        )}
      </Button>
    );
  }
);

ConfirmButton.displayName = 'ConfirmButton';

export { ConfirmButton };
