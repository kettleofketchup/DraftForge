import * as React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';
import { ScrollArea } from '~/components/ui/scroll-area';
import { cn } from '~/lib/utils';

export type FormDialogSize = 'sm' | 'md' | 'lg' | 'xl' | 'full';

export interface FormDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when open state changes */
  onOpenChange: (open: boolean) => void;
  /** Dialog title */
  title: string;
  /** Optional dialog description */
  description?: string;
  /** Form content */
  children: React.ReactNode;
  /** Submit button label */
  submitLabel?: string;
  /** Cancel button label */
  cancelLabel?: string;
  /** Whether form is submitting */
  isSubmitting?: boolean;
  /** Callback when submit is clicked */
  onSubmit: () => void | Promise<void>;
  /** Dialog size */
  size?: FormDialogSize;
  /** Whether to show the footer (default true) */
  showFooter?: boolean;
  /**
   * Whether the dialog should auto-focus its first focusable element on open
   * (Radix default). Set to `false` for forms that surface field-level
   * keyboard shortcuts — auto-focusing the first input swallows those
   * keystrokes until the user blurs out. Default: true.
   */
  autoFocus?: boolean;
  /** Additional class name for the dialog content */
  className?: string;
  /** Test ID for testing */
  'data-testid'?: string;
  /** Test ID for the title heading */
  titleTestId?: string;
}

const sizeClasses: Record<FormDialogSize, string> = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md md:max-w-lg',
  lg: 'sm:max-w-lg md:max-w-2xl',
  xl: 'sm:max-w-2xl md:max-w-4xl',
  full: 'sm:max-w-6xl',
};

/**
 * Standardized form dialog for create/edit operations.
 *
 * @example
 * <FormDialog
 *   open={showCreate}
 *   onOpenChange={setShowCreate}
 *   title="Create League"
 *   description="Add a new league to organize tournaments."
 *   submitLabel="Create"
 *   isSubmitting={isCreating}
 *   onSubmit={handleCreate}
 *   size="md"
 * >
 *   <FormFields />
 * </FormDialog>
 */
export const FormDialog = React.forwardRef<HTMLDivElement, FormDialogProps>(
  (
    {
      open,
      onOpenChange,
      title,
      description,
      children,
      submitLabel = 'Save',
      cancelLabel = 'Cancel',
      isSubmitting = false,
      onSubmit,
      size = 'md',
      showFooter = true,
      autoFocus = true,
      className,
      'data-testid': dataTestId,
      titleTestId,
    },
    ref
  ) => {
    // Internal ref to DialogContent so we can move focus into the dialog when
    // the caller opted out of Radix's auto-focus (otherwise focus stays on the
    // trigger element, which Radix immediately marks aria-hidden — focus +
    // aria-hidden on the same node is a screen-reader violation).
    const contentRef = React.useRef<HTMLDivElement | null>(null);
    const setContentRef = React.useCallback(
      (node: HTMLDivElement | null) => {
        contentRef.current = node;
        if (typeof ref === 'function') ref(node);
        else if (ref) ref.current = node;
      },
      [ref],
    );

    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      await onSubmit();
    };

    // Submit button lives in <DialogFooter> — outside the <form>. Browser
    // implicit Enter-submit can't reach it, so handle Enter ourselves at
    // the DialogContent level (catches focus-on-input, focus-on-content-div,
    // and focus-on-any-non-button descendant). Skip:
    //   - textarea / contenteditable: Enter inserts a newline
    //   - button: native Enter triggers click (Cancel/Submit handle themselves)
    //   - Radix popper items (SelectItem, MenuItem, Combobox option): React
    //     synthetic events bubble through the React tree even when the popper
    //     is portaled out of DialogContent in the DOM, so Enter-to-pick would
    //     otherwise also submit the form.
    const handleContentKeyDown = React.useCallback(
      (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key !== 'Enter' || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return;
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName;
        if (tag === 'TEXTAREA' || tag === 'BUTTON' || target?.isContentEditable) return;
        const role = target?.getAttribute('role');
        if (
          role === 'option' ||
          role === 'menuitem' ||
          role === 'menuitemradio' ||
          role === 'menuitemcheckbox' ||
          target?.closest('[role="listbox"], [role="menu"], [role="combobox"]')
        ) {
          return;
        }
        e.preventDefault();
        void onSubmit();
      },
      [onSubmit],
    );

    // Escape-to-blur via Radix's own onEscapeKeyDown — the sanctioned way to
    // suppress the dialog's close. Manually stopPropagation on a deeper React
    // handler doesn't reliably stop Radix because Radix binds at document
    // level. First Escape blurs the input; second Escape (focus now on body)
    // lets Radix close the dialog as usual.
    const handleEscapeKeyDown = React.useCallback((event: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      const tag = active?.tagName;
      const isEditable =
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        active?.isContentEditable;
      if (!isEditable || !active) return;
      event.preventDefault();
      (active as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).blur();
    }, []);

    // Stable handlers for Radix Dialog's outside-interaction props — these
    // were inline arrows previously, so each FormDialog re-render handed
    // DialogContent fresh function refs, which the Scan trace showed as
    // `onPointerDownOutside:28x onInteractOutside:28x` prop-changes.
    const preventOutside = React.useCallback(
      (e: Event) => e.preventDefault(),
      [],
    );

    // Suppress Radix's open-time auto-focus when the caller wants raw
    // focus (so field shortcuts like N / R / F start working immediately).
    // We still move focus *into* the dialog (onto the DialogContent itself,
    // which Radix marks tabindex=-1) so the trigger element doesn't keep
    // focus while being aria-hidden by Radix's outside-content masking.
    const handleOpenAutoFocus = React.useCallback(
      (e: Event) => {
        if (!autoFocus) {
          e.preventDefault();
          contentRef.current?.focus({ preventScroll: true });
        }
      },
      [autoFocus],
    );

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          ref={setContentRef}
          onKeyDown={handleContentKeyDown}
          className={cn(
            // Full-screen on mobile
            'h-full max-w-full rounded-none top-0 left-0 translate-x-0 translate-y-0',
            // Centered dialog on sm+
            'sm:h-auto sm:max-w-[calc(100%-2rem)] sm:rounded-lg sm:top-[50%] sm:left-[50%] sm:translate-x-[-50%] sm:translate-y-[-50%]',
            // Disable zoom animation for large dialogs - causes expensive layout calculations
            'data-[state=open]:!zoom-in-100 data-[state=closed]:!zoom-out-100',
            sizeClasses[size],
            className
          )}
          // Prevent outside-click dismissal: form dialogs should only close via
          // explicit actions (X, Cancel, submit). This also fixes nested dialog
          // issues where an inner dialog's overlay triggers the outer's dismiss.
          onPointerDownOutside={preventOutside}
          onInteractOutside={preventOutside}
          onEscapeKeyDown={handleEscapeKeyDown}
          onOpenAutoFocus={handleOpenAutoFocus}
          data-testid={dataTestId}
        >
          <DialogHeader>
            <DialogTitle data-testid={titleTestId}>{title}</DialogTitle>
            {description ? (
              <DialogDescription>{description}</DialogDescription>
            ) : (
              <DialogDescription className="sr-only">
                {title} dialog
              </DialogDescription>
            )}
          </DialogHeader>

          <ScrollArea className="max-h-[calc(100svh-10rem)] sm:max-h-[60vh] pr-4">
            {/* px-1 py-1 leaves room for focus rings (3px box-shadow on
                shadcn Input/Button) which would otherwise be clipped by
                Radix Viewport's overflow:hidden. */}
            <form
              onSubmit={handleSubmit}
              className="space-y-4 px-1 py-1"
            >
              {children}
            </form>
          </ScrollArea>

          {showFooter && (
            <DialogFooter className="flex-row justify-end gap-2">
              <CancelButton
                type="button"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
                hotkey="⌫"
                data-testid="modal-cancel-button"
              >
                {cancelLabel}
              </CancelButton>
              <ConfirmButton
                type="submit"
                onClick={handleSubmit}
                loading={isSubmitting}
                hotkey="↵"
                data-testid="form-dialog-submit"
              >
                {submitLabel}
              </ConfirmButton>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    );
  }
);

FormDialog.displayName = 'FormDialog';

export default FormDialog;
