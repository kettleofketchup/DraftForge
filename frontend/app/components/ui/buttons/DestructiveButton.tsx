import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import { brandErrorPrimary, buttonLift, buttonDisabled } from './styles';

export interface DestructiveButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Whether to apply the soft-shadow lift (default: true) */
  depth?: boolean;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

/**
 * A destructive action button with red styling and a soft-shadow lift.
 * Used for delete, remove, or other destructive actions.
 *
 * @example
 * ```tsx
 * <DestructiveButton onClick={handleDelete} loading={isDeleting}>
 *   Delete Item
 * </DestructiveButton>
 * ```
 */
const DestructiveButton = React.forwardRef<
  HTMLButtonElement,
  DestructiveButtonProps
>(({ loading = false, disabled, children, className, depth = true, hotkey, size, ...props }, ref) => {
  // min-h-11 is the 44px touch target for dialog footers, but it would override
  // an explicit size="sm"/"icon" and leave this button taller than the
  // Primary/Secondary siblings it sits beside in compact action rows.
  const touchTarget = size === 'sm' || size === 'icon' ? undefined : 'min-h-11';
  // When hotkey is unset, pass a single child so `asChild` callers stay valid
  // (Slot's React.Children.only rejects arrays — see SecondaryButton note).
  const inner = loading ? (
    <>
      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      Deleting...
    </>
  ) : (
    children
  );

  return (
    <Button
      ref={ref}
      disabled={disabled || loading}
      size={size}
      className={cn(
        // min-h-11 matches ConfirmButton/CancelButton so footer rows align.
        touchTarget,
        depth ? `${buttonLift} ${buttonDisabled} ${brandErrorPrimary} shadow-red-950/40` : brandErrorPrimary,
        hotkey && 'relative',
        className
      )}
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
});

DestructiveButton.displayName = 'DestructiveButton';

export { DestructiveButton };
