import { PlusCircle } from 'lucide-react'; // Or your preferred icon library
import React from 'react';
import { Button } from '~/components/ui/button'; // Adjust path as needed
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip'; // Adjust path as needed

interface DeleteButtonProps {
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  tooltipText?: string;
  ariaLabel?: string;
  className?: string; // Optional className prop for additional styling
}

export const AddButton: React.FC<DeleteButtonProps> = ({
  onClick,
  disabled = false,
  tooltipText = 'Delete item',
  ariaLabel = 'Delete',
  className = 'bg-success hover:bg-success/80 text-white', // Default className, can be overridden
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            size="icon"
            variant="outline"
            onClick={onClick}
            aria-label={ariaLabel}
            className={className} // You can adjust or remove this as needed
          >
            <PlusCircle color="green" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
