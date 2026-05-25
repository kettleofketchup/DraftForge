import { Crown } from 'lucide-react';
import React, { useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { TEAMS_BUTTONS_WIDTH } from '~/components/constants';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
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

// `?modal=captains` opens this dialog so it's bookmarkable / deep-linkable.
const MODAL_PARAM = 'modal';
const MODAL_VALUE = 'captains';

export const CaptainSelectionModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const isStaff = useUserStore((state) => state.isStaff());
  const TriggerButton = isStaff ? PrimaryButton : SecondaryButton;
  const [searchParams, setSearchParams] = useSearchParams();
  const open = searchParams.get(MODAL_PARAM) === MODAL_VALUE;
  const setOpen = useCallback(
    (next: boolean) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next) params.set(MODAL_PARAM, MODAL_VALUE);
          else if (params.get(MODAL_PARAM) === MODAL_VALUE) params.delete(MODAL_PARAM);
          return params;
        },
        { replace: true, preventScrollReset: true },
      );
    },
    [setSearchParams],
  );

  const dialogButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <TriggerButton
                className={`flex-1 sm:flex-none sm:w-[${TEAMS_BUTTONS_WIDTH}]`}
                data-testid="captain-modal-trigger"
              >
                <Crown className="mr-1.5 sm:mr-2" />
                <span className="sm:hidden">Captains</span>
                <span className="hidden sm:inline">Pick Captains</span>
              </TriggerButton>
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
            <SecondaryButton>Close</SecondaryButton>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
