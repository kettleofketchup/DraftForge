import { ChevronsLeft } from 'lucide-react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
interface PrevRoundButtonProps {
  goToPrevRound: () => void;
}
export const PrevRoundButton: React.FC<PrevRoundButtonProps> = ({
  goToPrevRound,
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button onClick={goToPrevRound} className="bg-sky-900" size="icon">
            <ChevronsLeft className="text-white" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>Go to the previous draft round</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
