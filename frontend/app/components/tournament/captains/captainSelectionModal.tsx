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
import { useUserStore } from '~/store/userStore';
import { CaptainTable } from './captainTable';
export const CaptainSelectionModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);

  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="btn btn-primary">Choose Captains</Button>
      </DialogTrigger>
      <DialogContent className=" xl:min-w-6xl l:min-w-5xl md:min-w-4xl sm:min-w-2xl min-w-l ">
        <DialogHeader>
          <DialogTitle>Choose Captains</DialogTitle>
          <DialogDescription>
            Update Captains for {tournament.name}
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-y-auto max-h-[70vh] pr-2">
          <CaptainTable />
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
