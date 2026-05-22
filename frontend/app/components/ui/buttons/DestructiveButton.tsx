import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { HotkeyBadge } from './HotkeyBadge';
import { brandErrorPrimary, button3DBase, button3DDisabled } from './styles';

export interface DestructiveButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
  /** Optional keyboard shortcut label rendered as a badge in the top-left corner. */
  hotkey?: string;
}

/**
 * A destructive action button with red styling and 3D depth effects.
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
>(({ loading = false, disabled, children, className, depth = true, hotkey, ...props }, ref) => {
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
      className={cn(
        // Bottom-border opacity bumped 50 → 80 so the 3D floor reads at the
        // same visual weight as <EditButton>'s emerald-900 floor. /50 was
        // making the destructive pill look ~2px shorter than its sibling.
        depth ? `${button3DBase} ${button3DDisabled} ${brandErrorPrimary} border-b-red-900/80 shadow-red-950/40` : brandErrorPrimary,
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
