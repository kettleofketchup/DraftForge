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
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { InitDraftButton } from './buttons/initDraftDialog';
import { DraftRoundCard } from './draftRoundCard';
import { DraftRoundView } from './draftRoundView';
import type { DraftRoundType, DraftType } from './types';
const log = getLogger('DraftModal');
export const DraftModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const [draftIndex, setDraftIndex] = useState<number>(0);
  const [open, setOpen] = useState(false);
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
    log.debug(curRound);
  };
  const nextRound = () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;
    log.debug('Next Round');
    log.debug('Current Index', draftIndex, draft.draft_rounds.length);

    // Fix: Check if next index is within bounds
    if (draftIndex < draft.draft_rounds.length - 1) {
      log.debug('Setting new round', draftIndex + 1, draft.draft_rounds.length);
      setCurDraftRound(draft.draft_rounds[draftIndex + 1]);
      setDraftIndex(draftIndex + 1);
    } else {
      log.debug('Already at the last round');
    }
    log.debug('Current round after update:', curRound);
  }; //localhost/api/tournaments/init-draft

  const totalRounds = (tournament?.teams?.length || 0) * 5;

  useEffect(() => {
    log.debug('Tournament draft data:', tournament?.draft);

    // Only set draft data if tournament and draft exist

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
  }, [tournament, setDraft, setCurDraftRound]);

  useEffect(() => {
    log.debug('Current draft round state:', curRound);
  }, [curRound]);

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
      <div className="flex items-center ">
        <DraftRoundCard
          draftRound={curRound}
          maxRounds={totalRounds}
          isCur={true}
        />

        {draftIndex < totalRounds &&
        draft &&
        draft.draft_rounds &&
        draft.draft_rounds[draftIndex + 1] ? (
          <div className="hidden lg:flex lg:w-full">
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
    );
  };
  const mainView = () => {
    if (!draft || !draft.draft_rounds) return <>{noDraftView()}</>;
    return <>{header()} </>;
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="btn btn-primary">
          <ClipboardPen /> Draft
        </Button>
      </DialogTrigger>

      <DialogContent className=" min-w-sm  xl:min-w-5xl l:min-w-5xl md:min-w-3xl sm:min-w-2xl ">
        <ScrollArea className="overflow-y-auto h-screen max-h-[80vh] py-5em pr-2">
          <DialogHeader>
            <DialogTitle>Tournament Draft</DialogTitle>
            <DialogDescription>Drafting Teams</DialogDescription>
            {mainView()}
          </DialogHeader>

          {curRound && Object.keys(curRound).length > 0 ? (
            <DraftRoundView />
          ) : (
            <div className="text-center p-4">
              <p>No draft round data available</p>
              <p className="text-sm text-gray-500">
                Tournament: {tournament?.name || 'None'}, Draft:{' '}
                {draft?.pk ? 'Available' : 'None'}, Rounds:{' '}
                {draft?.draft_rounds?.length || 0}
              </p>
            </div>
          )}
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
