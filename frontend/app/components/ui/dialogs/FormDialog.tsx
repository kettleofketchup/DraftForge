import * as React from 'react';
import { Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
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
}

const sizeClasses: Record<FormDialogSize, string> = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-lg',
  xl: 'sm:max-w-2xl',
  full: 'sm:max-w-4xl',
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
    },
    ref
  ) => {
    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      await onSubmit();
    };

    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          ref={ref}
          className={cn('max-w-[calc(100%-2rem)]', sizeClasses[size])}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>

          <ScrollArea className="max-h-[60vh] pr-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              {children}
            </form>
          </ScrollArea>

          {showFooter && (
            <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                {cancelLabel}
              </Button>
              <Button
                type="submit"
                onClick={handleSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {submitLabel}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    );
  }
);

FormDialog.displayName = 'FormDialog';

export default FormDialog;
