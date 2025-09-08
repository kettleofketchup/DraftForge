import { Crown } from 'lucide-react';
import React, { useState } from 'react';
import { TEAMS_BUTTONS_WIDTH } from '~/components/constants';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { useUserStore } from '~/store/userStore';
import { CaptainTable } from './captainTable';

export const CaptainSelectionModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const [open, setOpen] = useState(false);

  const dialogButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button
                className={`w-[${TEAMS_BUTTONS_WIDTH}] bg-yellow-400 hover:bg-yellow-200 text-black`}
              >
                <Crown className="mr-2" />
                Pick Captains
              </Button>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>Change Captains and Draft Order</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {dialogButton()}
      <DialogContent className={`${DIALOG_CSS}`}>
        <DialogHeader>
          <DialogTitle>Choose Captains</DialogTitle>
          <DialogDescription>
            Update Captains for {tournament.name}
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className={`${SCROLLAREA_CSS}`}>
          <CaptainTable />
          {/* Optional: Add a vertical scrollbar */}
          {/* Optional: Add a horizontal scrollbar */}
          <ScrollBar orientation="vertical" />
          <ScrollBar orientation="horizontal" />
        </ScrollArea>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
