import { ChevronsRight } from 'lucide-react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

interface NextRoundButtonProps {
  goToNextRound: () => void;
}
export const NextRoundButton: React.FC<NextRoundButtonProps> = ({
  goToNextRound,
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button onClick={goToNextRound} className="bg-sky-900" size="icon">
            <ChevronsRight className="text-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>Go to the next draft round</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
