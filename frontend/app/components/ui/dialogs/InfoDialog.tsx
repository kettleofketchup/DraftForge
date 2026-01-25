import * as React from 'react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { ScrollArea } from '~/components/ui/scroll-area';
import { cn } from '~/lib/utils';

export type InfoDialogSize = 'sm' | 'md' | 'lg';

export interface InfoDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when open state changes */
  onOpenChange: (open: boolean) => void;
  /** Dialog title */
  title: string;
  /** Dialog content */
  children: React.ReactNode;
  /** Dialog size */
  size?: InfoDialogSize;
  /** Whether to show close button in footer */
  showClose?: boolean;
  /** Close button label */
  closeLabel?: string;
}

const sizeClasses: Record<InfoDialogSize, string> = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-2xl',
};

/**
 * Standardized info dialog for displaying read-only information.
 *
 * @example
 * <InfoDialog
 *   open={showPlayer}
 *   onOpenChange={setShowPlayer}
 *   title="Player Details"
 *   size="md"
 * >
 *   <PlayerDetails player={player} />
 * </InfoDialog>
 */
export const InfoDialog = React.forwardRef<HTMLDivElement, InfoDialogProps>(
  (
    {
      open,
      onOpenChange,
      title,
      children,
      size = 'md',
      showClose = true,
      closeLabel = 'Close',
    },
    ref
  ) => {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          ref={ref}
          className={cn('max-w-[calc(100%-2rem)]', sizeClasses[size])}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>

          <ScrollArea className="max-h-[60vh] pr-4">
            {children}
          </ScrollArea>

          {showClose && (
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {closeLabel}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    );
  }
);

InfoDialog.displayName = 'InfoDialog';

export default InfoDialog;
