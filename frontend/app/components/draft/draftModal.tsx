import { ClipboardPen } from 'lucide-react';
import React, { useEffect, useState } from 'react';
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
import { ScrollArea } from '~/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { InitDraftButton } from './buttons/initDraftDialog';
import { DraftRoundCard } from './draftRoundCard';
import { DraftRoundView } from './draftRoundView';
import { useDraftLive } from './hooks/useDraftLive';
import type { DraftRoundType, DraftType } from './types';
const log = getLogger('DraftModal');
export const DraftModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const draftIndex = useUserStore((state) => state.draftIndex);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const [open, setOpen] = useState(false);

  // Enable live updates when modal is open and draft exists
  const { isPolling, forceRefresh } = useDraftLive({
    enabled: open && !!tournament?.draft?.pk,
    interval: 3000, // Poll every 3 seconds when modal is open
    onUpdate: () => {
      log.debug('Live update received - draft data refreshed');
    },
  });

  const prevRound = () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;
    log.debug('Prev Round');
    log.debug('Current Index', draftIndex, draft.draft_rounds.length);

    if (draftIndex > 0) {
      log.debug('Setting new round', draftIndex, draft.draft_rounds.length);
      setDraftIndex(draftIndex - 1);
      setCurDraftRound(draft.draft_rounds[draftIndex - 1]);
    }
    log.debug(draftIndex);
  };
  const nextRound = () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;
    log.debug('Next Round');
    log.debug('Current Index', draftIndex, draft.draft_rounds.length);

    // Fix: Check if next index is within bounds
    if (draftIndex < draft.draft_rounds.length - 1) {
      log.debug('Setting new round', draftIndex + 1, draft.draft_rounds.length);
      setDraftIndex(draftIndex + 1);
    } else {
      log.debug('Already at the last round');
    }
    log.debug('Current round after update:', curDraftRound);
  }; //localhost/api/tournaments/init-draft

  const totalRounds = (tournament?.teams?.length || 0) * 5;

  useEffect(() => {
    if (!draft || !draft.draft_rounds) return;
    log.debug('Setting current draft round based on index:', draftIndex);
    // Ensure we don't go out of bounds
    if (draftIndex < 0 || draftIndex >= draft.draft_rounds.length) {
      log.warn(
        `Draft index ${draftIndex} is out of bounds for available rounds: ${draft.draft_rounds.length}`,
      );
      return;
    }
    log.debug(
      `Setting current draft round to index ${draftIndex} with data:`,
      draft.draft_rounds[draftIndex],
    );
    setCurDraftRound(
      draft?.draft_rounds?.[draftIndex] || ({} as DraftRoundType),
    );
  }, [draftIndex]);
  const initialize = () => {
    log.debug('Tournament Modal Initialized draft data:', tournament?.draft);

    if (tournament?.draft) {
      setDraft(tournament.draft);

      // Only set current round if draft_rounds exist and has at least one round
      if (
        tournament.draft.draft_rounds &&
        tournament.draft.draft_rounds.length > 0
      ) {
        if (draftIndex <= 0) {
          setDraftIndex(0);
        }
        setCurDraftRound(tournament.draft.draft_rounds[0]);
        log.debug('Set initial draft round:', tournament.draft.draft_rounds[0]);
      } else {
        log.warn('No draft rounds available');
        setCurDraftRound({} as DraftRoundType);
      }
    } else {
      log.warn('No draft data available in tournament');
      setDraft({} as DraftType);
      setCurDraftRound({} as DraftRoundType);
    }
  };

  useEffect(() => {
    initialize();
  }, []);

  useEffect(() => {
    log.debug('Tournament Modal Initialized draft data:', tournament?.draft);
  }, [
    tournament,
    tournament.teams,
    setDraft,
    setCurDraftRound,
    setDraftIndex,
    tournament.teams,
  ]);

  useEffect(() => {
    log.debug('Current draft round state:', curDraftRound);
  }, [draftIndex]);

  // Log modal state changes for debugging live updates
  useEffect(() => {
    if (open) {
      log.debug('Draft modal opened - live updates should start');
    } else {
      log.debug('Draft modal closed - live updates should stop');
    }
  }, [open]);

  const noDraftView = () => {
    return (
      <>
        <h1> No Draft Information Available</h1>
        <p> Start the draft with the init draft button below</p>
      </>
    );
  };

  const header = () => {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold">Draft Progress</h3>
            {tournament?.draft?.pk && (
              <div className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    isPolling ? 'bg-success animate-pulse' : 'bg-warning'
                  }`}
                />
                <span className="text-xs text-base-content/70">
                  {isPolling ? 'Live updates' : 'Manual refresh only'}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center">
          <DraftRoundCard
            draftRound={
              draft?.draft_rounds?.[draftIndex] || ({} as DraftRoundType)
            }
            maxRounds={totalRounds}
            isCur={true}
          />

          {draftIndex < totalRounds &&
          draft &&
          draft.draft_rounds &&
          draft.draft_rounds[draftIndex + 1] ? (
            <div className="hidden lg:flex lg:w-full lg:pl-8">
              <DraftRoundCard
                draftRound={draft.draft_rounds[draftIndex + 1]}
                maxRounds={totalRounds}
                isCur={false}
              />
            </div>
          ) : (
            <></>
          )}
        </div>
      </div>
    );
  };
  const mainView = () => {
    if (!draft || !draft.draft_rounds) return <>{noDraftView()}</>;
    return (
      <>
        {header()}
        <DraftRoundView />
      </>
    );
  };

  const draftDialogButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button className="btn btn-primary">
                <ClipboardPen />
                Begin Draft
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
      {draftDialogButton()}

      <DialogContent className=" min-w-sm  xl:min-w-5xl l:min-w-5xl md:min-w-3xl sm:min-w-2xl ">
        <ScrollArea className="overflow-y-auto h-screen max-h-[80vh] py-5em pr-2">
          <DialogHeader>
            <DialogTitle>Tournament Draft</DialogTitle>
            <DialogDescription>Drafting Teams</DialogDescription>
            {mainView()}
          </DialogHeader>
        </ScrollArea>

        <DialogFooter className="flex flex-col items-center gap-4 mb-4 md:flex-row">
          <InitDraftButton />

          <Button
            className="w-40 sm:w-40 md:w-40 btn btn-info"
            onClick={prevRound}
          >
            Prev Round
          </Button>
          <Button className="w-40 btn btn-info" onClick={nextRound}>
            Next Round
          </Button>

          <DialogClose asChild>
            <Button className="w-40">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
