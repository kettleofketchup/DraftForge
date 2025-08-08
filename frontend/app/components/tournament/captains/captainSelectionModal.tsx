import { Crown } from 'lucide-react';
import React, { useState } from 'react';
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
              <Button className="btn btn-primary">
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
      <DialogContent className="xl:min-w-5xl l:min-w-5xl md:min-w-3xl sm:min-w-2xl  ">
        <DialogHeader>
          <DialogTitle>Choose Captains</DialogTitle>
          <DialogDescription>
            Update Captains for {tournament.name}
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[70vh] w-full border rounded-md px-1 overflow-x-auto">
          <CaptainTable />
          <ScrollBar orientation="vertical" />{' '}
          {/* Optional: Add a vertical scrollbar */}
          <ScrollBar orientation="horizontal" />{' '}
          {/* Optional: Add a horizontal scrollbar */}
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
