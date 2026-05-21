import * as React from 'react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import {
  CancelButton,
  ConfirmButton,
  brandReadableDestructive,
  brandReadableSuccess,
  brandReadableWarning,
  brandSuccessBg,
} from '~/components/ui/buttons';
import type { CancelButtonVariant, ConfirmButtonVariant } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface ConfirmDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when open state changes */
  onOpenChange: (open: boolean) => void;
  /** Dialog title */
  title: string;
  /** Dialog description (string or React node — use a node for richer recaps like UserStrip + details) */
  description: React.ReactNode;
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
  /** data-testid for the AlertDialogContent root */
  contentTestId?: string;
  /** data-testid for the AlertDialogTitle */
  titleTestId?: string;
  /** data-testid for the AlertDialogDescription */
  descriptionTestId?: string;
  /** Optional content rendered between header and footer as a sibling grid row.
   *  When omitted, NO wrapper element is emitted (the 13 existing call sites
   *  see identical layout). */
  bodyContent?: React.ReactNode;
  /** When true, the confirm button is rendered disabled regardless of isLoading. */
  confirmDisabled?: boolean;
}

// Content background styling per variant
const contentVariantStyles = {
  default: `bg-green-900 ${brandSuccessBg}`,
  destructive: 'bg-red-950/95 border-red-800',
  warning: 'bg-orange-950/95 border-orange-800',
};

// Body text per variant — uses the tonal-harmony brand readables so the copy
// picks up the surface hue family without competing with the gradient. Each
// constant bakes in font-medium + a hair of letter-spacing for sub-pixel
// sharpness over color.
const descriptionVariantStyles = {
  default: brandReadableSuccess,
  destructive: brandReadableDestructive,
  warning: brandReadableWarning,
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
      contentTestId,
      titleTestId,
      descriptionTestId,
      bodyContent,
      confirmDisabled = false,
    },
    ref
  ) => {
    const handleConfirm = async () => {
      if (isLoading || confirmDisabled) return;
      await onConfirm();
      onOpenChange(false);
    };

    const handleCancel = () => {
      if (isLoading) return;
      onOpenChange(false);
    };

    // Enter → confirm, Backspace → cancel. Escape is already handled by Radix.
    // We skip the keys when an editable element has focus so users can still
    // type in inputs nested inside `description`.
    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.defaultPrevented || isLoading) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isEditable =
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        target?.isContentEditable;
      if (isEditable) return;

      if (event.key === 'Enter') {
        event.preventDefault();
        void handleConfirm();
      } else if (event.key === 'Backspace') {
        event.preventDefault();
        handleCancel();
      }
    };

    return (
      <AlertDialog open={open} onOpenChange={onOpenChange}>
        <AlertDialogContent
          ref={ref}
          onKeyDown={handleKeyDown}
          data-testid={contentTestId}
          className={cn(
            'max-w-[calc(100%-2rem)] sm:max-w-md',
            contentVariantStyles[variant]
          )}
        >
          <AlertDialogHeader>
            <AlertDialogTitle data-testid={titleTestId}>{title}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div
                data-testid={descriptionTestId}
                className={cn('text-sm', descriptionVariantStyles[variant])}
              >
                {description}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {bodyContent ? <div data-testid="confirm-dialog-body-slot">{bodyContent}</div> : null}
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-3">
            <CancelButton
              onClick={handleCancel}
              disabled={isLoading}
              variant={cancelVariant ?? (variant === 'warning' ? 'success' : 'default')}
              hotkey="⌫"
              data-testid={cancelTestId}
            >
              {cancelLabel}
            </CancelButton>
            <ConfirmButton
              onClick={handleConfirm}
              loading={isLoading}
              disabled={confirmDisabled}
              variant={confirmButtonVariantMap[variant]}
              hotkey="↵"
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
