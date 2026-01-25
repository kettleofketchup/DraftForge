import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { button3DVariants } from './styles';

export type CancelButtonVariant = 'default' | 'success' | 'destructive';

export interface CancelButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
  /** Color variant - 'success' for green cancel (e.g., in warning dialogs) */
  variant?: CancelButtonVariant;
}

/**
 * A cancel button with outline styling and optional 3D depth effects.
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
  ({ children = 'Cancel', className, depth = true, variant = 'default', ...props }, ref) => {
    const variantStyles = {
      default: depth ? button3DVariants.outline : '',
      success: depth ? button3DVariants.success : 'bg-green-600 text-white hover:bg-green-500',
      destructive: depth ? button3DVariants.destructive : 'bg-red-600 text-white hover:bg-red-500',
    };

    return (
      <Button
        ref={ref}
        variant={variant === 'default' ? 'outline' : undefined}
        className={cn(variantStyles[variant], className)}
        {...props}
      >
        {children}
      </Button>
    );
  }
);

CancelButton.displayName = 'CancelButton';

export { CancelButton };
