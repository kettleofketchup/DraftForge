import { BarChart3, ChevronUp, ClipboardPen, EyeIcon } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { Button } from '~/components/ui/button';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { getLogger } from '~/lib/logger';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { TEAMS_BUTTONS_WIDTH } from '../constants';
import { DIALOG_CSS_FULLSCREEN } from '../reusable/modal';
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
import { useDraftWebSocketStore, draftWsSelectors } from '~/store/draftWebSocketStore';
import { LiveAutoButtons, DraftRoundIndicator } from './liveView';
import type { DraftRoundType, DraftType } from './types';
import type { TournamentType } from '~/components/tournament/types';
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
  // Note: Don't call setLive here - TournamentDetailPage handles live state based on URL
  const handleOpenChange = useCallback((isOpen: boolean) => {
    setOpen(isOpen);
    if (pk) {
      if (isOpen) {
        // Add /draft to URL when opening - TournamentDetailPage will set live=true
        navigate(`/tournament/${pk}/teams/draft`, { replace: true });
      } else {
        // Remove /draft from URL when closing - TournamentDetailPage will set live=false
        navigate(`/tournament/${pk}/teams`, { replace: true });
      }
    }
  }, [pk, navigate]);

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
      // Note: Backend now includes tournament with teams in the WebSocket payload
      const draftState = wsState as DraftType & { tournament?: TournamentType };
      log.debug('WebSocket draft state update:', draftState);

      // Update the draft in the store
      setDraft(draftState);

      // CRITICAL: Update tournament synchronously if included in WebSocket payload
      // This ensures teams data is updated atomically with draft state
      if (draftState.tournament) {
        log.debug('WebSocket includes tournament data, updating synchronously');
        // Merge with existing tournament to preserve fields not in the payload
        const currentTournament = tournamentRef.current;
        const mergedTournament = {
          ...currentTournament,
          ...draftState.tournament,
          // Preserve draft reference from the new draft state
          draft: draftState,
        };
        setTournament(mergedTournament as TournamentType);
      }

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

      // Fallback: refresh tournament if not included in WebSocket payload
      if (!draftState.tournament) {
        const currentTournament = tournamentRef.current;
        if (currentTournament?.pk) {
          log.debug('WebSocket missing tournament data, fetching via API');
          refreshTournamentHook({
            tournament: currentTournament,
            setTournament,
          });
        }
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

  // WebSocket store state
  const wsStatus = useDraftWebSocketStore((s) => s.status);
  const wsConnected = useDraftWebSocketStore(draftWsSelectors.isConnected);
  const draftEvents = useDraftWebSocketStore((s) => s.events);
  const wsDraftState = useDraftWebSocketStore((s) => s.draftState);
  const hasNewEvent = useDraftWebSocketStore((s) => s.hasNewEvent);
  const clearNewEventFlag = useDraftWebSocketStore((s) => s.clearNewEventFlag);
  const wsConnect = useDraftWebSocketStore((s) => s.connect);
  const wsDisconnect = useDraftWebSocketStore((s) => s.disconnect);

  // Connect/disconnect WebSocket based on modal open state and draft availability
  useEffect(() => {
    if (open && draft?.pk) {
      wsConnect(draft.pk);
    }
    return () => {
      // Only disconnect when modal closes, not on every effect rerun
      if (!open) {
        wsDisconnect();
      }
    };
  }, [open, draft?.pk, wsConnect, wsDisconnect]);

  // React to WebSocket draft state updates
  useEffect(() => {
    if (wsDraftState) {
      handleDraftStateUpdate(wsDraftState);
    }
  }, [wsDraftState, handleDraftStateUpdate]);

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

  // Auto-refresh draft only as fallback when WebSocket is disconnected
  // Note: wsConnected is now read from store internally
  const { refresh: autoRefreshDraft } = useAutoRefreshDraft({
    enabled: open,
    curDraftRound,
    draft,
    setDraft,
    interval: 5000, // Fallback polling interval when WebSocket disconnected
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

  // Track if we've initialized for this draft to avoid duplicate init in Strict Mode
  const initializedDraftPk = useRef<number | null>(null);

  // Initialize draft data when tournament.draft becomes available
  useEffect(() => {
    // Skip initialization if tournament or draft not loaded yet
    if (!tournament?.pk || !tournament?.draft?.pk) {
      return;
    }

    // Skip if already initialized for this draft
    if (initializedDraftPk.current === tournament.draft.pk) {
      return;
    }

    log.debug('Initializing draft data from tournament:', tournament.draft.pk);
    initializedDraftPk.current = tournament.draft.pk;

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
      log.debug('No draft rounds available yet');
      setCurDraftRound({} as DraftRoundType);
    }
  }, [tournament?.pk, tournament?.draft?.pk]);

  // Log modal state changes for debugging live updates
  useEffect(() => {
    if (open) {
      log.debug('Draft modal opened - live updates should start');
    } else {
      log.debug('Draft modal closed - live updates should stop');
    }
  }, [open]);

  const mainView = () => {
    return (
      <>
        <DraftBalanceDisplay />
        <DraftRoundView />
      </>
    );
  };

  const draftDialogButton = () => {
    return (
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

      <DialogContent
        className={cn(DIALOG_CSS_FULLSCREEN, 'bg-gray-900')}
        closeButtonVariant="destructive"
        closeButtonTestId="close-draft-modal"
      >
        {/* Visually hidden but accessible title */}
        <DialogHeader className="sr-only">
          <DialogTitle>Tournament Draft</DialogTitle>
          <DialogDescription>Drafting Teams</DialogDescription>
        </DialogHeader>

        {/* Full screen layout */}
        <div className="flex flex-col h-full w-full overflow-hidden">
          {/* Top bar: Live/Auto buttons left, Draft round centered */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 shrink-0">
            <LiveAutoButtons isPolling={livePolling} />
            <DraftRoundIndicator />
            {/* Spacer to balance (close button is on right) */}
            <div className="w-[120px]" />
          </div>

          {/* Main content area */}
          <div className="flex-1 overflow-auto p-2 md:p-4">
            {mainView()}
          </div>

          {/* Footer - fixed at bottom */}
          <div className="shrink-0 border-t border-gray-800 bg-gray-900/95 backdrop-blur">
            {/* Mobile Footer Drawer */}
            <div className="md:hidden">
              <Collapsible open={footerDrawerOpen} onOpenChange={setFooterDrawerOpen}>
                <div className="flex items-center justify-between p-2">
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
                <CollapsibleContent className="border-t border-gray-800 bg-gray-800/50 p-4 space-y-3">
                  {/* Actions visible to everyone */}
                  <div className="flex flex-wrap gap-2 justify-center">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <SecondaryButton color="lime" onClick={() => setDraftStyleOpen(true)}>
                          <BarChart3 className="h-4 w-4 mr-2" />
                          Stats
                        </SecondaryButton>
                      </TooltipTrigger>
                      <TooltipContent>View Draft Balance Stats</TooltipContent>
                    </Tooltip>
                    <DraftHistoryButton
                      events={draftEvents}
                      hasNewEvent={hasNewEvent}
                      onViewed={clearNewEventFlag}
                    />
                    <ShareDraftButton />
                  </div>
                  {/* Moderation actions - only visible to staff */}
                  {isStaff() && (
                    <div className="flex flex-wrap gap-2 justify-center">
                      <DraftModerationDropdown onOpenDraftStyleModal={() => setDraftStyleOpen(true)} />
                      <UndoPickButton />
                    </div>
                  )}
                </CollapsibleContent>
              </Collapsible>
            </div>

            {/* Desktop Footer */}
            <div className="hidden md:flex w-full items-center justify-between gap-4 p-3">
              <div className="flex items-center gap-2">
                {/* Moderation actions - only visible to staff */}
                <DraftModerationDropdown onOpenDraftStyleModal={() => setDraftStyleOpen(true)} />
                <UndoPickButton />
                {/* Balance stats - visible to everyone */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton color="lime" onClick={() => setDraftStyleOpen(true)}>
                      <BarChart3 className="h-4 w-4 mr-2" />
                      Stats
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent>View Draft Balance Stats</TooltipContent>
                </Tooltip>
              </div>
              {choiceButtons()}
              <div className="flex items-center gap-2">
                <DraftHistoryButton
                  events={draftEvents}
                  hasNewEvent={hasNewEvent}
                  onViewed={clearNewEventFlag}
                />
                <ShareDraftButton />
              </div>
            </div>
          </div>
        </div>

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
