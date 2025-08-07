import { UserLock } from 'lucide-react';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
interface AdminOnlyButtonProps {
  buttonTxt?: string;
  tooltipTxt?: string;
}

export const AdminOnlyButton: React.FC<AdminOnlyButtonProps> = ({
  buttonTxt = 'Must be Admin',
  tooltipTxt = 'Be sure you are logged in. This request will fail if you are not a staff member or admin.',
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button className="btn btn-danger bg-red-900 text-white">
            <UserLock className="mr-2" />
            {buttonTxt}
          </Button>
        </TooltipTrigger>
        <TooltipContent className="bg-red-900 text-white rounded-lg">
          <div className="text-wrap text-center ">{tooltipTxt}</div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
