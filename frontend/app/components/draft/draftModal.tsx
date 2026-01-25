import { ChevronUp, ClipboardPen, EyeIcon, X } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { refreshDraftHook } from './hooks/refreshDraftHook';
import { refreshTournamentHook } from './hooks/refreshTournamentHook';
import { useAutoRefreshDraft } from './hooks/useAutoRefreshDraft';
import { useDraftLive } from './hooks/useDraftLive';
import { useDraftWebSocket } from './hooks/useDraftWebSocket';
import { LiveView } from './liveView';
import type { DraftRoundType, DraftType } from './types';
const log = getLogger('DraftModal');
type DraftModalParams = {};
export const DraftModal: React.FC<DraftModalParams> = ({}) => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const draftIndex = useUserStore((state) => state.draftIndex);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const setAutoRefreshDraft = useUserStore(
    (state) => state.setAutoRefreshDraft,
  );
  const live = useTournamentStore((state) => state.live);
  const livePolling = useTournamentStore((state) => state.livePolling);
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);
  const setLive = useTournamentStore((state) => state.setLive);
  const activeTab = useTournamentStore((state) => state.activeTab);
  const [open, setOpen] = useState(live);
  const [draftStyleOpen, setDraftStyleOpen] = useState(false);
  const [footerDrawerOpen, setFooterDrawerOpen] = useState(false);
  const isStaff = useUserStore((state) => state.isStaff);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { pk } = useParams<{ pk: string }>();

  // Sync URL with modal open/close state
  const handleOpenChange = useCallback((isOpen: boolean) => {
    setOpen(isOpen);
    if (pk) {
      if (isOpen) {
        // Add /draft to URL when opening
        navigate(`/tournament/${pk}/${activeTab}/draft`, { replace: true });
        setLive(true);
      } else {
        // Remove /draft from URL when closing
        navigate(`/tournament/${pk}/${activeTab}`, { replace: true });
        setLive(false);
      }
    }
  }, [pk, activeTab, navigate, setLive]);

  // Auto-open modal when ?draft=open is in URL (from share URL)
  useEffect(() => {
    const draftParam = searchParams.get('draft');
    if (draftParam === 'open') {
      setOpen(true);
      // Enable auto-advance when opened via share URL
      setAutoAdvance(true);
      // Remove the param after opening to avoid re-opening on navigation
      searchParams.delete('draft');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, setAutoAdvance]);

  useEffect(() => {
    if (live) {
      setOpen(true);
    }
  }, [live]);

  // Enable live updates when modal is open and draft exists

  const setDraftRoundToLatest = () => {
    const newDraft: DraftRoundType =
      draft?.draft_rounds?.find(
        (round: DraftRoundType) => round.pk === draft?.latest_round,
      ) || ({} as DraftRoundType);

    setCurDraftRound(newDraft);

    const i = draft?.draft_rounds?.findIndex(
      (round: DraftRoundType) => round.pk === newDraft.pk,
    );
    if (i) setDraftIndex(i);
    log.debug('Set draft round to latest:', { newDraft, i });
    log.debug('Current round after update:', curDraftRound);
  };

  const onUpdate = useCallback(() => {
    if (livePolling) {
      log.debug('Auto advance is enabled, refreshing draft and tournament');
      refreshDraftHook({ draft, setDraft });
      refreshTournamentHook({ tournament, setTournament });
    }
    if (autoAdvance) {
      setDraftRoundToLatest();
    }
  }, [autoAdvance, draft, setDraft, tournament, setTournament]);

  // WebSocket for real-time draft events
  // Use refs to avoid recreating callback on every render
  const tournamentRef = useRef(tournament);
  const curDraftRoundRef = useRef(curDraftRound);
  const autoAdvanceRef = useRef(autoAdvance);

  useEffect(() => {
    tournamentRef.current = tournament;
  }, [tournament]);

  useEffect(() => {
    curDraftRoundRef.current = curDraftRound;
  }, [curDraftRound]);

  useEffect(() => {
    autoAdvanceRef.current = autoAdvance;
  }, [autoAdvance]);

  // Handle draft state updates directly from WebSocket (avoids API calls)
  const handleDraftStateUpdate = useCallback(
    (wsState: unknown) => {
      // Cast to DraftType - the backend sends matching structure
      const draftState = wsState as DraftType;
      log.debug('WebSocket draft state update:', draftState);

      // Update the draft in the store
      setDraft(draftState);

      // Find and update the current draft round with new data
      const currentDraftRound = curDraftRoundRef.current;
      if (currentDraftRound?.pk && draftState.draft_rounds) {
        const updatedRound = draftState.draft_rounds.find(
          (round: DraftRoundType) => round.pk === currentDraftRound.pk,
        );
        if (updatedRound) {
          setCurDraftRound(updatedRound);
        }
      }

      // Auto-advance to latest round if enabled
      if (autoAdvanceRef.current && draftState.latest_round) {
        const latestRound = draftState.draft_rounds?.find(
          (round: DraftRoundType) => round.pk === draftState.latest_round,
        );
        if (latestRound) {
          log.debug('Auto-advancing to latest round:', latestRound.pk);
          setCurDraftRound(latestRound);
          const i = draftState.draft_rounds?.findIndex(
            (round: DraftRoundType) => round.pk === latestRound.pk,
          );
          if (i !== undefined && i >= 0) {
            setDraftIndex(i);
          }
        }
      }

      // Also refresh tournament to get updated team MMR data
      const currentTournament = tournamentRef.current;
      if (currentTournament?.pk) {
        refreshTournamentHook({
          tournament: currentTournament,
          setTournament,
        });
      }
    },
    [setDraft, setCurDraftRound, setDraftIndex, setTournament],
  );

  // Fallback refresh for when draft state is not included in WebSocket message
  const handleWebSocketRefresh = useCallback(async () => {
    const currentTournament = tournamentRef.current;
    const currentDraftRound = curDraftRoundRef.current;
    if (currentTournament?.pk) {
      log.debug('WebSocket triggered refresh (fallback)');
      await refreshTournamentHook({
        tournament: currentTournament,
        setTournament,
        setDraft,
        curDraftRound: currentDraftRound,
        setCurDraftRound,
      });
    }
  }, [setTournament, setDraft, setCurDraftRound]);

  const {
    events: draftEvents,
    isConnected: wsConnected,
    hasNewEvent,
    clearNewEventFlag,
  } = useDraftWebSocket({
    draftId: draft?.pk ?? null,
    onDraftStateUpdate: handleDraftStateUpdate,
    onRefreshNeeded: handleWebSocketRefresh,
  });

  // Auto-advance to latest round when latest_round changes and autoAdvance is enabled
  // Uses primitive value (draft?.latest_round) to avoid infinite loops from object reference changes
  useEffect(() => {
    if (autoAdvance && draft?.latest_round) {
      setDraftRoundToLatest();
    }
  }, [draft?.latest_round, autoAdvance]);

  // Only use polling as fallback when WebSocket is not connected
  const draftLiveOptions = useMemo(
    () => ({
      enabled: open && !!tournament?.draft?.pk && livePolling && !wsConnected,
      interval: 3000, // Poll every 3 seconds when modal is open and WS disconnected
      onUpdate,
    }),
    [open, tournament?.draft?.pk, livePolling, wsConnected, onUpdate],
  );

  const { isPolling, forceRefresh } = useDraftLive(draftLiveOptions);

  // Auto-refresh draft every second when current captain choice is null
  const { refresh: autoRefreshDraft } = useAutoRefreshDraft({
    enabled: open,
    curDraftRound,
    draft,
    setDraft,
    interval: 1000,
  });

  // Store refresh function in userStore so other components can access it
  useEffect(() => {
    setAutoRefreshDraft(autoRefreshDraft);
    return () => setAutoRefreshDraft(null);
  }, [autoRefreshDraft, setAutoRefreshDraft]);

  const goToLatestRound = async () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;

    const newDraft: DraftRoundType =
      draft?.draft_rounds?.find(
        (round: DraftRoundType) => round.pk === draft?.latest_round,
      ) || ({} as DraftRoundType);

    setCurDraftRound(newDraft);

    const i = draft?.draft_rounds?.findIndex(
      (round: DraftRoundType) => round.pk === newDraft.pk,
    );

    if (i == -1) {
      setCurDraftRound(draft?.draft_rounds[-1]);
    }
    if (i !== undefined && i !== draftIndex) {
      log.debug('Setting draft index to latest round index:', i);
      setDraftIndex(i);
    }

    log.debug('Set draft round to latest:', { newDraft, i });
    log.debug('Current round after update:', curDraftRound);
  };

  const prevRound = async () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;
    log.debug('Prev Round');
    log.debug('Current Index', draftIndex, draft.draft_rounds.length);
    const i = draftIndex;

    if (i > 0) {
      log.debug('Setting new round', draftIndex, draft.draft_rounds.length);
      setDraftIndex(i - 1);
      setCurDraftRound(draft.draft_rounds[i - 1]);
    }
  };

  const nextRound = async () => {
    if (!draft) return;
    if (!draft.draft_rounds) return;
    const i = draftIndex;
    log.debug('Next Round');
    log.debug('Current Index', draftIndex, draft.draft_rounds.length);
    // Fix: Check if next index is within bounds
    if (i < draft.draft_rounds.length - 1) {
      log.debug('Setting new round', i + 1, draft.draft_rounds.length);
      setDraftIndex(i + 1);
      setCurDraftRound(draft?.draft_rounds?.[i + 1] || ({} as DraftRoundType));
    } else {
      log.debug('Already at the last round');
    }
    log.debug('Current round after update:', curDraftRound);
  };

  useEffect(() => {
    log.debug(
      'rerender: Tournament Modal Initialized draft data:',
      tournament?.draft,
    );

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
  }, []);

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
