import { ChevronUp, ClipboardPen, EyeIcon, X } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { Button } from '~/components/ui/button';
import { DestructiveButton } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
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
import { cn } from '~/lib/utils';
import { getLogger } from '~/lib/logger';
import { useTournamentStore } from '~/store/tournamentStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useUserStore } from '~/store/userStore';
import { TEAMS_BUTTONS_WIDTH } from '../constants';
import { DIALOG_CSS, SCROLLAREA_CSS } from '../reusable/modal';
import { DraftHistoryButton } from './buttons/DraftHistoryButton';
import { DraftModerationDropdown } from './buttons/DraftModerationDropdown';
import { DraftStyleModal } from './buttons/draftStyleModal';
import { LatestRoundButton } from './buttons/latestButton';
import { NextRoundButton } from './buttons/nextButton';
import { PrevRoundButton } from './buttons/prevButton';
import { ShareDraftButton } from './buttons/shareDraftButton';
import { UndoPickButton } from './buttons/undoPickButton';
import { DraftBalanceDisplay } from './draftBalanceDisplay';
import { DraftRoundView } from './draftRoundView';
import { LiveView } from './liveView';

const log = getLogger('DraftModal');

type DraftModalParams = {};

export const DraftModal: React.FC<DraftModalParams> = ({}) => {
  // Tournament data from new store
  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const tournament = useTournamentDataStore((state) => state.tournament);

  // Draft state from new store (includes WebSocket)
  // Only subscribe to latest_round for auto-advance (not the whole draft object)
  const latestRound = useTeamDraftStore((state) => state.draft?.latest_round);
  const draftEvents = useTeamDraftStore((state) => state.events);
  const hasNewEvent = useTeamDraftStore((state) => state.hasNewEvent);
  const clearNewEventFlag = useTeamDraftStore((state) => state.clearNewEvent);
  const setDraftId = useTeamDraftStore((state) => state.setDraftId);
  const reset = useTeamDraftStore((state) => state.reset);
  const goToLatestRoundAction = useTeamDraftStore((state) => state.goToLatestRound);
  const previousRoundAction = useTeamDraftStore((state) => state.previousRound);
  const nextRoundAction = useTeamDraftStore((state) => state.nextRound);

  // UI state from tournament store
  const live = useTournamentStore((state) => state.live);
  const livePolling = useTournamentStore((state) => state.livePolling);
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);

  // Local UI state
  const [open, setOpen] = useState(live);
  const [draftStyleOpen, setDraftStyleOpen] = useState(false);
  const [footerDrawerOpen, setFooterDrawerOpen] = useState(false);
  const isStaff = useUserStore((state) => state.isStaff);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { pk } = useParams<{ pk: string }>();

  // Initialize draft store when modal opens
  useEffect(() => {
    if (open && tournament?.draft?.pk && tournamentId) {
      setDraftId(tournament.draft.pk, tournamentId);
    }
    return () => {
      // Cleanup on unmount or when modal closes
      reset();
    };
  }, [open, tournament?.draft?.pk, tournamentId, setDraftId, reset]);

  // Sync URL with modal open/close state
  const handleOpenChange = useCallback((isOpen: boolean) => {
    setOpen(isOpen);
    if (pk) {
      if (isOpen) {
        navigate(`/tournament/${pk}/teams/draft`, { replace: true });
      } else {
        navigate(`/tournament/${pk}/teams`, { replace: true });
      }
    }
  }, [pk, navigate]);

  // Auto-open modal when ?draft=open is in URL (from share URL)
  useEffect(() => {
    const draftParam = searchParams.get('draft');
    if (draftParam === 'open') {
      setOpen(true);
      setAutoAdvance(true);
      searchParams.delete('draft');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, setAutoAdvance]);

  // Sync with live state from URL
  useEffect(() => {
    if (live) {
      setOpen(true);
    }
  }, [live]);

  // Auto-advance to latest round when autoAdvance is enabled and draft updates
  useEffect(() => {
    if (autoAdvance && latestRound) {
      goToLatestRoundAction();
    }
  }, [autoAdvance, latestRound, goToLatestRoundAction]);

  // Navigation handlers using store methods
  const goToLatestRound = useCallback(() => {
    goToLatestRoundAction();
  }, [goToLatestRoundAction]);

  const prevRound = useCallback(() => {
    previousRoundAction();
  }, [previousRoundAction]);

  const nextRound = useCallback(() => {
    nextRoundAction();
  }, [nextRoundAction]);

  // Log modal state changes for debugging live updates
  useEffect(() => {
    if (open) {
      log.debug('Draft modal opened - live updates should start');
    } else {
      log.debug('Draft modal closed - live updates should stop');
    }
  }, [open]);

  const header = () => {
    return (
      <div className="flex flex-col gap-1">
        <LiveView isPolling={livePolling} />
        <DraftBalanceDisplay />
      </div>
    );
  };

  const mainView = () => {
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
              <Button
                className={`w-[${TEAMS_BUTTONS_WIDTH}] ${!isStaff() ? 'bg-green-800 hover:bg-green-600' : 'bg-sky-800 hover:bg-sky-600'} text-white`}
              >
                {!isStaff() ? <EyeIcon /> : <ClipboardPen />}
                {!isStaff() ? 'Live Draft' : 'Start Draft'}
              </Button>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>
              {!isStaff()
                ? 'Watch The live draft in progress'
                : 'Administer the Draft'}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  const choiceButtons = () => {
    return (
      <div className="w-full flex  gap-4 align-center justify-center ">
        <PrevRoundButton goToPrevRound={prevRound} />
        <LatestRoundButton goToLatestRound={goToLatestRound} />
        <NextRoundButton goToNextRound={nextRound} />
      </div>
    );
  };
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {draftDialogButton()}

      <DialogContent className={DIALOG_CSS}>
        <ScrollArea className={SCROLLAREA_CSS}>
          <DialogHeader>
            <DialogTitle>Tournament Draft</DialogTitle>
            <DialogDescription>Drafting Teams</DialogDescription>
            {mainView()}
          </DialogHeader>
          <ScrollBar orientation="vertical" />
          <ScrollBar orientation="horizontal" />
        </ScrollArea>

        {/* Mobile Footer Drawer */}
        <div className="md:hidden">
          <Collapsible open={footerDrawerOpen} onOpenChange={setFooterDrawerOpen}>
            <div className="flex items-center justify-between p-2 border-t">
              {choiceButtons()}
              <CollapsibleTrigger asChild>
                <Button variant="outline" size="sm" className="ml-2">
                  <ChevronUp className={cn(
                    "h-4 w-4 transition-transform",
                    footerDrawerOpen && "rotate-180"
                  )} />
                  <span className="ml-1">Actions</span>
                </Button>
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent className="border-t bg-muted/50 p-4 space-y-3">
              <div className="flex flex-wrap gap-2 justify-center">
                <DraftModerationDropdown onOpenDraftStyleModal={() => setDraftStyleOpen(true)} />
                <UndoPickButton />
              </div>
              <div className="flex flex-wrap gap-2 justify-center">
                <DraftHistoryButton
                  events={draftEvents}
                  hasNewEvent={hasNewEvent}
                  onViewed={clearNewEventFlag}
                />
                <ShareDraftButton />
              </div>
              <div className="flex justify-center">
                <DialogClose asChild>
                  <DestructiveButton onClick={() => handleOpenChange(false)}>
                    <X className="h-4 w-4 mr-1" />
                    Close
                  </DestructiveButton>
                </DialogClose>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>

        {/* Desktop Footer */}
        <DialogFooter
          id="DraftFootStarter"
          className="hidden md:flex w-full flex-col rounded-full items-center gap-4 mb-4 md:flex-row align-center sm:shadow-md sm:shadow-black/10 /50 sm:p-6 sm:m-0"
        >
          <div className="flex w-full justify-center md:justify-start gap-2">
            <DraftModerationDropdown onOpenDraftStyleModal={() => setDraftStyleOpen(true)} />
            <UndoPickButton />
          </div>
          {choiceButtons()}
          <div className="flex w-full justify-center md:justify-end gap-2">
            <DraftHistoryButton
              events={draftEvents}
              hasNewEvent={hasNewEvent}
              onViewed={clearNewEventFlag}
            />
            <ShareDraftButton />

            <DialogClose asChild>
              <DestructiveButton onClick={() => handleOpenChange(false)}>
                <X className="h-4 w-4 mr-1" />
                Close
              </DestructiveButton>
            </DialogClose>
          </div>
        </DialogFooter>

        {/* Externally controlled Draft Style Modal */}
        <DraftStyleModal
          externalOpen={draftStyleOpen}
          onExternalOpenChange={setDraftStyleOpen}
          showTrigger={false}
        />
      </DialogContent>
    </Dialog>
  );
};
