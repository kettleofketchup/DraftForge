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

import { motion } from 'framer-motion';
export const AdminOnlyButton: React.FC<AdminOnlyButtonProps> = ({
  buttonTxt = 'Must be Admin',
  tooltipTxt = 'Be sure you are logged in. This request will fail if you are not a staff member or admin.',
}) => {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <motion.div
            whileInView={{
              opacity: 1,
              transition: { delay: 0.05, duration: 0.5 },
            }}
            whileHover={{ scale: 1.1 }}
            whileFocus={{ scale: 1.05 }}
            
          >
            <Button className="btn btn-danger bg-red-900 text-white">
              <UserLock className="mr-2" />
              {buttonTxt}
            </Button>
          </motion.div>
        </TooltipTrigger>
        <TooltipContent className="bg-red-900 text-white rounded-lg">
          <div className="text-wrap text-center ">{tooltipTxt}</div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
