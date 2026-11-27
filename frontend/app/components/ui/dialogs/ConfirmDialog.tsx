import * as React from 'react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '~/components/ui/alert-dialog';
import type {
  CancelButtonVariant,
  ConfirmButtonVariant,
} from '~/components/ui/buttons';
import {
  CancelButton,
  ConfirmButton,
  brandDestructiveBg,
  brandReadableDestructive,
  brandReadableSuccess,
  brandReadableWarning,
  brandSuccessBg,
  brandWarningBg,
} from '~/components/ui/buttons';
import { cn } from '~/lib/utils';

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Dialog description (string or React node — use a node for richer recaps like UserStrip + details) */
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'destructive' | 'warning';
  /** Cancel button variant - overrides default variant-based logic */
  cancelVariant?: CancelButtonVariant;
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
  confirmTestId?: string;
  cancelTestId?: string;
  /** data-testid for the AlertDialogContent root */
  contentTestId?: string;
  /** data-testid for the AlertDialogTitle */
  titleTestId?: string;
  /** data-testid for the AlertDialogDescription */
  descriptionTestId?: string;
  /** Optional sibling grid row between header and footer; no wrapper when omitted. */
  bodyContent?: React.ReactNode;
  /** When true, the confirm button is rendered disabled regardless of isLoading. */
  confirmDisabled?: boolean;
}

const contentVariantStyles = {
  default: `bg-success-surface ${brandSuccessBg}`,
  destructive: `bg-background ${brandDestructiveBg} border-destructive/50`,
  warning: `bg-background ${brandWarningBg} border-warning/40`,
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

const confirmButtonVariantMap: Record<string, ConfirmButtonVariant> = {
  default: 'default',
  destructive: 'destructive',
  warning: 'warning',
};

/**
 * Standardized confirmation dialog for destructive or important actions.
 * Uses reusable ConfirmButton and CancelButton components with a soft-shadow lift.
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
export const ConfirmDialog = React.forwardRef<
  HTMLDivElement,
  ConfirmDialogProps
>(
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
    ref,
  ) => {
    const contentRef = React.useRef<HTMLDivElement | null>(null);
    const setContentRef = React.useCallback(
      (node: HTMLDivElement | null) => {
        contentRef.current = node;
        if (typeof ref === 'function') ref(node);
        else if (ref) ref.current = node;
      },
      [ref],
    );

    // Opening one dialog while another is still animating closed leaves focus
    // in the closing one, so Enter/Backspace would never reach this one. Take
    // focus as soon as the content exists, before the next key event.
    React.useLayoutEffect(() => {
      const el = contentRef.current;
      if (open && el && !el.contains(document.activeElement)) {
        el.focus({ preventScroll: true });
      }
    }, [open]);

    // Don't hand focus back to the page if another dialog is already open.
    const handleCloseAutoFocus = (event: Event) => {
      if (
        document.querySelector(
          '[role="alertdialog"][data-state="open"], [role="dialog"][data-state="open"]',
        )
      ) {
        event.preventDefault();
      }
    };

    const handleConfirm = async () => {
      if (isLoading || confirmDisabled) return;
      try {
        await onConfirm();
      } finally {
        onOpenChange(false);
      }
    };

    const handleCancel = () => {
      if (isLoading) return;
      onOpenChange(false);
    };

    // Enter confirms unless a button, link, or role="button" has focus;
    // Backspace cancels. Radix handles Escape. Editable elements are skipped
    // so users can type in inputs nested inside `description`.
    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
      // A closing dialog keeps focus during its exit animation; ignore its keys.
      if (!open || event.defaultPrevented || isLoading) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isEditable =
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        target?.isContentEditable;
      if (isEditable) return;

      if (event.key === 'Enter') {
        if (target?.closest('button, a[href], [role="button"]')) return;
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
          ref={setContentRef}
          onKeyDown={handleKeyDown}
          onCloseAutoFocus={handleCloseAutoFocus}
          data-testid={contentTestId}
          className={cn(
            'max-w-[calc(100%-2rem)] sm:max-w-md',
            contentVariantStyles[variant],
          )}
        >
          <AlertDialogHeader>
            <AlertDialogTitle data-testid={titleTestId}>
              {title}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div
                data-testid={descriptionTestId}
                className={cn('text-sm', descriptionVariantStyles[variant])}
              >
                {description}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {bodyContent ? (
            <div data-testid="confirm-dialog-body-slot">{bodyContent}</div>
          ) : null}
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-3">
            <CancelButton
              onClick={handleCancel}
              disabled={isLoading}
              variant={
                cancelVariant ?? (variant === 'warning' ? 'success' : 'default')
              }
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
  },
);

ConfirmDialog.displayName = 'ConfirmDialog';

export default ConfirmDialog;
