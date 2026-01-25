import { Loader2 } from 'lucide-react';
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export interface DestructiveButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether the button is in a loading state */
  loading?: boolean;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
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
>(({ loading = false, disabled, children, className, depth = true, ...props }, ref) => {
  return (
    <Button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        depth ? button3DVariants.destructive : 'bg-red-600 text-white hover:bg-red-500',
        className
      )}
      {...props}
    >
      {loading ? (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          Deleting...
        </>
      ) : (
        children
      )}
    </Button>
  );
});

DestructiveButton.displayName = 'DestructiveButton';

export { DestructiveButton };
