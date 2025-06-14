import React from 'react';
import { Button } from '~/components/ui/button'; // Adjust path as needed
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed
import { Trash2 } from 'lucide-react'; // Or your preferred icon library
import { memo } from 'react';

interface DeleteButtonProps {
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  tooltipText?: string;
  ariaLabel?: string;
  className?: string; // Optional className prop for additional styling
}
export const DeleteButton: React.FC<DeleteButtonProps> = memo(
  ({
    onClick,
    disabled = false,
    tooltipText = 'Delete item',
    ariaLabel = 'Delete',
    className = 'bg-red-950 hover:bg-red-600 text-white',
  }) => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={onClick}
              disabled={disabled}
              aria-label={ariaLabel}
              className={className}
            >
              <Trash2 className="h-4 w-4" color="red" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{tooltipText}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  },
);
