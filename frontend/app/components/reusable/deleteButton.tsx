import React, { memo, useState } from 'react';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { TrashIconButton } from '~/components/ui/buttons';
import { TooltipContent } from '~/components/ui/tooltip';

interface DeleteButtonProps {
  onClick: (event?: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  tooltipText?: string;
  ariaLabel?: string;
  className?: string;
  /** If true, shows a confirmation dialog before executing onClick */
  requireConfirmation?: boolean;
  /** Title for the confirmation dialog */
  confirmTitle?: string;
  /** Description for the confirmation dialog */
  confirmDescription?: string;
}

interface DeleteTooltipProps {
  tooltipText?: string;
}

export const DeleteButtonTooltip: React.FC<DeleteTooltipProps> = memo(
  ({ tooltipText = 'Delete item' }) => {
    return (
      <TooltipContent>
        <p>{tooltipText}</p>
      </TooltipContent>
    );
  },
);

export const DeleteButton: React.FC<DeleteButtonProps> = memo(
  ({
    onClick,
    disabled = false,
    tooltipText = 'Delete item',
    className,
    requireConfirmation = false,
    confirmTitle = 'Delete Item?',
    confirmDescription = 'This action cannot be undone.',
  }) => {
    const [open, setOpen] = useState(false);

    const handleClick = (e?: React.MouseEvent<HTMLButtonElement>) => {
      if (requireConfirmation) {
        setOpen(true);
      } else {
        onClick(e);
      }
    };

    const handleConfirm = () => {
      onClick();
      setOpen(false);
    };

    return (
      <>
        <TrashIconButton
          size="sm"
          onClick={handleClick}
          disabled={disabled}
          tooltip={tooltipText}
          className={className}
        />
        {requireConfirmation && (
          <ConfirmDialog
            open={open}
            onOpenChange={setOpen}
            title={confirmTitle}
            description={confirmDescription}
            confirmLabel="Delete"
            variant="destructive"
            onConfirm={handleConfirm}
          />
        )}
      </>
    );
  },
);
