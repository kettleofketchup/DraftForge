import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

interface LatestRoundButtonProps {
  goToLatestRound: () => void;
}
export const LatestRoundButton: React.FC<LatestRoundButtonProps> = ({
  goToLatestRound,
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button className="bg-sky-900 text-white" onClick={goToLatestRound}>
            Latest
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>Go to the latest draft round</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
