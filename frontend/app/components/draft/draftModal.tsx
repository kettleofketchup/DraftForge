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
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { Badge } from '../ui/badge';
import DraftView from './draftView';
import { InitDraftButton } from './initDraftDialog';
import type { DraftType, DraftRoundType } from './types';

const log = getLogger('DraftModal');
export const DraftModal: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
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
  };

  const totalRounds = (tournament?.teams?.length || 0) * 5;

  useEffect(() => {
    log.debug('Tournament draft data:', tournament?.draft);

    // Only set draft data if tournament and draft exist
    if (tournament?.draft) {
      setDraft(tournament.draft);

      // Only set current round if draft_rounds exist and has at least one round
      if (tournament.draft.draft_rounds && tournament.draft.draft_rounds.length > 0) {
        setDraftIndex(0);
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
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="btn btn-primary">
          <ClipboardPen /> Draft
        </Button>
      </DialogTrigger>
      <DialogContent className=" xl:min-w-6xl l:min-w-5xl md:min-w-4xl sm:min-w-2xl min-w-l ">
        <DialogHeader>
          <DialogTitle>Tournament Draft</DialogTitle>
          <DialogDescription>Drafting Teams</DialogDescription>
        </DialogHeader>

        <div className="flex flex-row items-center gap-4 mb-4">
          <Badge>
            Round {curRound?.pick_number ?? 0}/{totalRounds}
          </Badge>
          <span>
            Current Captain:
            {curRound?.captain?.nickname || curRound?.captain?.username || 'No captain selected'}
          </span>
          <InitDraftButton />
        </div>
        <div className="overflow-y-auto max-h-[70vh] pr-2">
          {curRound && Object.keys(curRound).length > 0 ? (
            <DraftView curRound={curRound} />
          ) : (
            <div className="text-center p-4">
              <p>No draft round data available</p>
              <p className="text-sm text-gray-500">
                Tournament: {tournament?.name || 'None'},
                Draft: {draft?.pk ? 'Available' : 'None'},
                Rounds: {draft?.draft_rounds?.length || 0}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <div className="flex flex-row items-center gap-4 mb-4">
            <Button className="btn btn-info" onClick={prevRound}>
              Prev Round
            </Button>
            <Button className="btn btn-info" onClick={nextRound}>
              Next Round
            </Button>
          </div>
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
