import * as React from 'react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import { CancelButton, ConfirmButton, brandSuccessBg } from '~/components/ui/buttons';
import type { CancelButtonVariant, ConfirmButtonVariant } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface ConfirmDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when open state changes */
  onOpenChange: (open: boolean) => void;
  /** Dialog title */
  title: string;
  /** Dialog description */
  description: string;
  /** Confirm button label */
  confirmLabel?: string;
  /** Cancel button label */
  cancelLabel?: string;
  /** Visual variant - affects styling */
  variant?: 'default' | 'destructive' | 'warning';
  /** Cancel button variant - overrides default variant-based logic */
  cancelVariant?: CancelButtonVariant;
  /** Whether the action is in progress */
  isLoading?: boolean;
  /** Callback when confirm is clicked */
  onConfirm: () => void | Promise<void>;
  /** data-testid for confirm button */
  confirmTestId?: string;
  /** data-testid for cancel button */
  cancelTestId?: string;
}

// Content background styling per variant
const contentVariantStyles = {
  default: `bg-green-900 ${brandSuccessBg}`,
  destructive: 'bg-red-950/95 border-red-800',
  warning: 'bg-orange-950/95 border-orange-800',
};

// Description text styling per variant
const descriptionVariantStyles = {
  default: '',
  destructive: 'text-slate-300',
  warning: 'text-orange-200',
};

// Map dialog variant to button variants
const confirmButtonVariantMap: Record<string, ConfirmButtonVariant> = {
  default: 'default',
  destructive: 'destructive',
  warning: 'warning',
};

/**
 * Standardized confirmation dialog for destructive or important actions.
 * Uses reusable ConfirmButton and CancelButton components with 3D depth effects.
 *
 * @example
 * <ConfirmDialog
 *   open={showDelete}
 *   onOpenChange={setShowDelete}
 *   title="Delete Tournament?"
 *   description="This action cannot be undone."
 *   confirmLabel="Delete"
 *   variant="destructive"
 *   isLoading={isDeleting}
 *   onConfirm={handleDelete}
 * />
 */
export const ConfirmDialog = React.forwardRef<HTMLDivElement, ConfirmDialogProps>(
  (
    {
      open,
      onOpenChange,
      title,
      description,
      confirmLabel = 'Confirm',
      cancelLabel = 'Cancel',
      variant = 'default',
      cancelVariant,
      isLoading = false,
      onConfirm,
      confirmTestId,
      cancelTestId,
    },
    ref
  ) => {
    const handleConfirm = async () => {
      await onConfirm();
      onOpenChange(false);
    };

    const handleCancel = () => {
      onOpenChange(false);
    };

    return (
      <AlertDialog open={open} onOpenChange={onOpenChange}>
        <AlertDialogContent
          ref={ref}
          className={cn(
            'max-w-[calc(100%-2rem)] sm:max-w-md',
            contentVariantStyles[variant]
          )}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            <AlertDialogDescription
              className={cn(descriptionVariantStyles[variant])}
            >
              {description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-3">
            <CancelButton
              onClick={handleCancel}
              disabled={isLoading}
              variant={cancelVariant ?? (variant === 'warning' ? 'success' : 'default')}
              data-testid={cancelTestId}
            >
              {cancelLabel}
            </CancelButton>
            <ConfirmButton
              onClick={handleConfirm}
              loading={isLoading}
              variant={confirmButtonVariantMap[variant]}
              data-testid={confirmTestId}
            >
              {confirmLabel}
            </ConfirmButton>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }
);

ConfirmDialog.displayName = 'ConfirmDialog';

export default ConfirmDialog;
