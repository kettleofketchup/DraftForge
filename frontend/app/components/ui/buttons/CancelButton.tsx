import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import { brandNeutralOpaque, brandNeutralOpaqueLift, brandButtonVariants } from './styles';

export type CancelButtonVariant = 'default' | 'success' | 'destructive';

export interface CancelButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
  /** Color variant - 'success' for green cancel (e.g., in warning dialogs) */
  variant?: CancelButtonVariant;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

/**
 * A cancel button with outline styling and an optional soft-shadow lift.
 * Can be wrapped with DialogClose for dialog dismissal.
 *
 * @example
 * ```tsx
 * <CancelButton onClick={handleCancel}>Cancel</CancelButton>
 *
 * // Green cancel button for warning dialogs
 * <CancelButton variant="success">Cancel</CancelButton>
 *
 * // Red cancel button for destructive emphasis
 * <CancelButton variant="destructive">Cancel</CancelButton>
 *
 * // With DialogClose
 * <DialogClose asChild>
 *   <CancelButton>Cancel</CancelButton>
 * </DialogClose>
 * ```
 */
const CancelButton = React.forwardRef<HTMLButtonElement, CancelButtonProps>(
  ({ children = 'Cancel', className, depth = true, variant = 'default', hotkey, ...props }, ref) => {
    const variantStyles = {
      default: depth ? brandNeutralOpaqueLift : brandNeutralOpaque,
      success: depth ? brandButtonVariants.success : 'bg-green-600 text-white hover:bg-green-500',
      destructive: depth ? brandButtonVariants.destructive : 'bg-red-600 text-white hover:bg-red-500',
    };

    // When hotkey is unset, pass children as the single child so `asChild`
    // callers stay valid (Slot's React.Children.only rejects arrays).
    return (
      <Button
        ref={ref}
        // No variant prop — brand styles fully control appearance via className.
        // Passing variant="outline" introduces dark: prefixed classes that override brand bg.
        className={cn('min-h-11', variantStyles[variant], hotkey && 'relative', className)}
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
  }
);

CancelButton.displayName = 'CancelButton';

export { CancelButton };
