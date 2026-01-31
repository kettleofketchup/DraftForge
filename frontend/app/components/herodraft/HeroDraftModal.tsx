// frontend/app/components/herodraft/HeroDraftModal.tsx
import { useCallback, useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "~/components/ui/dialog";
import { VisuallyHidden } from "~/components/ui/visually-hidden";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { useHeroDraftStore, heroDraftSelectors } from "~/store/heroDraftStore";
import { useUserStore } from "~/store/userStore";
import { DraftTopBar } from "./DraftTopBar";
import { HeroGrid } from "./HeroGrid";
import { DraftPanel } from "./DraftPanel";
import { HeroDraftHistoryModal } from "./HeroDraftHistoryModal";
import { CompletedDraftView } from "./CompletedDraftView";
import { submitPick, setReady, triggerRoll, submitChoice, pauseDraft, resumeDraft } from "./api";
import type { HeroDraft, HeroDraftEvent } from "./types";
import { DisplayName } from "~/components/user/avatar";
import { getHeroIcon, getHeroName as getHeroNameFromLib } from "~/lib/dota/heroes";
import { CaptainToast, HeroActionToast } from "./DraftToasts";
import { Send, ArrowLeft, Users, Pause, Play } from "lucide-react";
import { HistoryButton } from "~/components/ui/buttons";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog";

interface HeroDraftModalProps {
  draftId: number;
  open: boolean;
  onClose: () => void;
}

export function HeroDraftModal({ draftId, open, onClose }: HeroDraftModalProps) {
  const navigate = useNavigate();
  const { currentUser } = useUserStore();

  // WebSocket store - unified state and connection management
  const draft = useHeroDraftStore((state) => state.draft);
  const tick = useHeroDraftStore((state) => state.tick);
  const lastEvent = useHeroDraftStore((state) => state.lastEvent);
  const setSelectedHeroId = useHeroDraftStore((state) => state.setSelectedHeroId);
  const wsConnect = useHeroDraftStore((state) => state.connect);
  const wsDisconnect = useHeroDraftStore((state) => state.disconnect);
  const wsReconnect = useHeroDraftStore((state) => state.reconnect);
  const startHeartbeat = useHeroDraftStore((state) => state.startHeartbeat);
  const isConnected = useHeroDraftStore(heroDraftSelectors.isConnected);
  const connectionError = useHeroDraftStore((state) => state.error);
  const wasKicked = useHeroDraftStore((state) => state.wasKicked);

  const [confirmHeroId, setConfirmHeroId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [resumeCountdown, setResumeCountdown] = useState<number | null>(null);
  const [pendingChoice, setPendingChoice] = useState<{
    type: "pick_order" | "side";
    value: "first" | "second" | "radiant" | "dire";
  } | null>(null);
  const [showFullDraft, setShowFullDraft] = useState(false);

  // Close handler - navigates to bracket if tournament context exists, otherwise calls onClose
  const handleClose = useCallback(() => {
    if (draft?.tournament_id && draft?.game) {
      navigate(`/tournament/${draft.tournament_id}/bracket/match/${draft.game}`);
    } else {
      onClose();
    }
  }, [draft?.tournament_id, draft?.game, navigate, onClose]);

  // Connect/disconnect WebSocket based on modal open state
  useEffect(() => {
    if (open && draftId) {
      wsConnect(draftId);
    }
    return () => {
      if (!open) {
        wsDisconnect();
      }
    };
  }, [open, draftId, wsConnect, wsDisconnect]);

  // Handle events from WebSocket - show toasts
  useEffect(() => {
    if (!lastEvent) return;

    console.log("[HeroDraftModal] handleEvent:", lastEvent.event_type, lastEvent);

    const draftTeam = lastEvent.draft_team;
    const captain = draftTeam?.captain;

    switch (lastEvent.event_type) {
      case "captain_ready":
        toast(<CaptainToast captain={captain} message="is ready" messageClassName="text-blue-400 font-semibold" />);
        break;
      case "captain_connected":
        toast(<CaptainToast captain={captain} message="connected" messageClassName="text-green-500 font-semibold" />);
        break;
      case "captain_disconnected":
        toast(<CaptainToast captain={captain} message="disconnected" messageClassName="text-red-500 font-semibold" />);
        break;
      case "draft_paused":
        toast.warning("Draft paused - waiting for captain to reconnect");
        setResumeCountdown(null);
        break;
      case "resume_countdown": {
        const countdownSeconds = (lastEvent.metadata as { countdown_seconds?: number })?.countdown_seconds ?? 3;
        setResumeCountdown(countdownSeconds);
        toast.info(`Resuming in ${countdownSeconds}...`);
        break;
      }
      case "draft_resumed":
        toast.success("Draft resumed - all captains connected");
        setResumeCountdown(null);
        break;
      case "roll_result":
        toast(<CaptainToast captain={captain} message="won the coin flip!" messageClassName="text-yellow-400 font-semibold" />);
        break;
      case "hero_selected": {
        const heroId = lastEvent.metadata?.hero_id;
        const actionType = lastEvent.metadata?.action_type;
        const heroName = heroId ? getHeroNameFromLib(heroId) : "Unknown Hero";
        const heroIconUrl = heroId ? getHeroIcon(heroId) : undefined;
        const action = actionType === "ban" ? "banned" : "picked";

        toast(<HeroActionToast captain={captain} action={action} heroName={heroName} heroIconUrl={heroIconUrl} />);
        break;
      }
      case "draft_completed":
        toast.success("Draft completed!");
        break;
    }
  }, [lastEvent]);

  // Countdown timer effect - decrements every second
  useEffect(() => {
    if (resumeCountdown === null || resumeCountdown <= 0) return;

    const timer = setTimeout(() => {
      setResumeCountdown((prev) => (prev !== null && prev > 0 ? prev - 1 : null));
    }, 1000);

    return () => clearTimeout(timer);
  }, [resumeCountdown]);

  // Start heartbeat when connected as captain
  // Note: isCaptain check requires draft to be loaded, so we check both
  const isCaptainForHeartbeat = draft?.draft_teams.some((t) => t.captain?.pk === currentUser?.pk);
  useEffect(() => {
    if (isConnected && isCaptainForHeartbeat) {
      startHeartbeat();
    }
  }, [isConnected, isCaptainForHeartbeat, startHeartbeat]);

  // Show toast when kicked
  useEffect(() => {
    if (wasKicked) {
      toast.error("Connection replaced - you opened this draft in another tab");
    }
  }, [wasKicked]);

  // Alias for backwards compatibility
  const reconnect = wsReconnect;

  const handleHeroClick = useCallback((heroId: number) => {
    if (!draft || !currentUser?.pk) {
      return;
    }

    const myTeam = draft.draft_teams.find((t) => t.captain?.pk === currentUser.pk);
    if (!myTeam) {
      return;
    }

    // Find current round from rounds array using current_round index
    const currentRound = draft.current_round !== null ? draft.rounds[draft.current_round] : null;

    if (!currentRound || currentRound.draft_team !== myTeam.id) {
      toast.error("It's not your turn");
      return;
    }

    setConfirmHeroId(heroId);
  }, [draft, currentUser]);

  const handleConfirmPick = async () => {
    console.log("[HeroDraftModal] handleConfirmPick:", {
      confirmHeroId,
      draft_id: draft?.id,
      draft_state: draft?.state,
      draft_current_round: draft?.current_round,
      isSubmitting,
    });

    if (!confirmHeroId || !draft || isSubmitting) {
      console.log("[HeroDraftModal] handleConfirmPick - early return:", {
        no_confirmHeroId: !confirmHeroId,
        no_draft: !draft,
        isSubmitting,
      });
      return;
    }

    setIsSubmitting(true);
    console.log("[HeroDraftModal] handleConfirmPick - calling submitPick...");
    try {
      // Don't call setDraft - WebSocket broadcasts state to all clients
      await submitPick(draft.id, confirmHeroId);
      console.log("[HeroDraftModal] handleConfirmPick - submitPick completed successfully");
      setConfirmHeroId(null);
      setSelectedHeroId(null);
    } catch (error: unknown) {
      console.error("[HeroDraftModal] handleConfirmPick - submitPick failed:", error);
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to submit pick");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReady = async () => {
    if (!draft || isSubmitting) return;
    setIsSubmitting(true);
    try {
      // Don't call setDraft here - WebSocket will broadcast the updated state
      // to all clients. Calling setDraft with API response can cause race conditions
      // where stale API data overwrites fresher WebSocket data.
      await setReady(draft.id);
      toast.success("You are ready!");
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to set ready");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTriggerRoll = async () => {
    if (!draft || isSubmitting) return;
    setIsSubmitting(true);
    try {
      // Don't call setDraft - WebSocket broadcasts state to all clients
      await triggerRoll(draft.id);
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to trigger roll");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePause = async () => {
    if (!draft || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await pauseDraft(draft.id);
      toast.success("Draft paused");
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to pause draft");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResume = async () => {
    if (!draft || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await resumeDraft(draft.id);
      toast.success("Resuming draft...");
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to resume draft");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChoiceSubmit = async (
    choiceType: "pick_order" | "side",
    value: string
  ) => {
    if (!draft || isSubmitting) return;
    setIsSubmitting(true);
    try {
      // Don't call setDraft - WebSocket broadcasts state to all clients
      await submitChoice(
        draft.id,
        choiceType,
        value as "first" | "second" | "radiant" | "dire"
      );
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to submit choice");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Helper to get readable choice labels
  const getChoiceLabel = (type: "pick_order" | "side", value: string) => {
    const labels: Record<string, string> = {
      first: "First Pick",
      second: "Second Pick",
      radiant: "Radiant",
      dire: "Dire",
    };
    return labels[value] || value;
  };

  // Confirm pending choice - called when user confirms in dialog
  const confirmPendingChoice = async () => {
    if (!pendingChoice) return;
    await handleChoiceSubmit(pendingChoice.type, pendingChoice.value);
    setPendingChoice(null);
  };

  // Find current round from rounds array
  const currentRoundData = draft && draft.current_round !== null
    ? draft.rounds[draft.current_round]
    : null;

  // Check if it's my team's turn (either as captain or team member)
  const currentPickingTeam = currentRoundData
    ? draft?.draft_teams.find((t) => t.id === currentRoundData.draft_team)
    : null;
  const isMyTurn = currentPickingTeam
    ? currentPickingTeam.captain?.pk === currentUser?.pk ||
      currentPickingTeam.members?.some((m) => m.pk === currentUser?.pk)
    : false;

  const isCaptain = draft?.draft_teams.some((t) => t.captain?.pk === currentUser?.pk);
  // Find my team - either as captain or as a member
  const myTeam = draft?.draft_teams.find((t) =>
    t.captain?.pk === currentUser?.pk ||
    t.members?.some((m) => m.pk === currentUser?.pk)
  );
  const isOnTeam = !!myTeam;
  // roll_winner is already the full DraftTeam object from the backend
  const rollWinnerTeam = draft?.roll_winner ?? null;

  const currentAction = currentRoundData?.action_type;

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
        <DialogContent
          className="!fixed !inset-0 !translate-x-0 !translate-y-0 !top-0 !left-0 !max-w-none !w-full !h-full !p-0 !gap-0 !rounded-none !border-0 bg-gray-900 overflow-hidden"
          showCloseButton={false}
          data-testid="herodraft-modal"
          // Prevent closing from backdrop clicks or escape key - only close via the Close button
          // This prevents issues with AlertDialog interactions triggering Dialog close
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          <VisuallyHidden>
            <DialogTitle>Hero Draft</DialogTitle>
            <DialogDescription>Captain's Mode hero draft interface</DialogDescription>
          </VisuallyHidden>
          {draft && (
            <div className="flex flex-col h-full w-full bg-gray-900 overflow-hidden" data-testid="herodraft-container">
              {/* Top Bar */}
              <DraftTopBar draft={draft} tick={tick} />

              {/* Pre-draft phases */}
              {draft.state === "waiting_for_captains" && (
                <div className="flex-1 flex items-center justify-center" data-testid="herodraft-waiting-phase">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold" data-testid="herodraft-waiting-title">Waiting for Captains</h2>
                    <div className="flex gap-8" data-testid="herodraft-captain-status-list">
                      {draft.draft_teams.map((team) => (
                        <div key={team.id} className="text-center" data-testid={`herodraft-captain-status-${team.id}`}>
                          <p className="font-semibold" data-testid={`herodraft-captain-name-${team.id}`}>
                            {team.captain ? DisplayName(team.captain) : 'Unknown'}
                          </p>
                          <p
                            className={
                              team.is_ready ? "text-green-400" : "text-yellow-400"
                            }
                            data-testid={`herodraft-ready-status-${team.id}`}
                          >
                            {team.is_ready ? "Ready" : "Not Ready"}
                          </p>
                        </div>
                      ))}
                    </div>
                    {isCaptain && !myTeam?.is_ready && (
                      <Button onClick={handleReady} disabled={isSubmitting} data-testid="herodraft-ready-button">
                        {isSubmitting ? "Submitting..." : "Ready"}
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "rolling" && (
                <div className="flex-1 flex items-center justify-center" data-testid="herodraft-rolling-phase">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold" data-testid="herodraft-rolling-title">Both Captains Ready!</h2>
                    <p data-testid="herodraft-rolling-instruction">Click to trigger the coin flip</p>
                    {isCaptain && (
                      <Button onClick={handleTriggerRoll} disabled={isSubmitting} data-testid="herodraft-flip-coin-button">
                        {isSubmitting ? "Flipping..." : "Flip Coin"}
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "choosing" && (
                <div className="flex-1 flex items-center justify-center" data-testid="herodraft-choosing-phase">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold" data-testid="herodraft-flip-winner">
                      {rollWinnerTeam?.captain ? DisplayName(rollWinnerTeam.captain) : 'Unknown'} won the flip!
                    </h2>
                    {rollWinnerTeam?.id === myTeam?.id ? (
                      // Winner's turn - but check if they already made their choice
                      myTeam.is_first_pick !== null || myTeam.is_radiant !== null ? (
                        // Winner already made their choice, waiting for loser
                        <p data-testid="herodraft-winner-waiting">
                          Waiting for opponent to choose...
                        </p>
                      ) : (
                        <div className="space-y-2" data-testid="herodraft-winner-choices">
                          <p>Choose your preference:</p>
                          <div className="flex gap-4 justify-center" data-testid="herodraft-choice-buttons">
                            <Button
                              onClick={() => setPendingChoice({ type: "pick_order", value: "first" })}
                              disabled={isSubmitting}
                              data-testid="herodraft-choice-first-pick"
                            >
                              {isSubmitting ? "..." : "First Pick"}
                            </Button>
                            <Button
                              onClick={() => setPendingChoice({ type: "pick_order", value: "second" })}
                              disabled={isSubmitting}
                              data-testid="herodraft-choice-second-pick"
                            >
                              {isSubmitting ? "..." : "Second Pick"}
                            </Button>
                            <Button
                              onClick={() => setPendingChoice({ type: "side", value: "radiant" })}
                              disabled={isSubmitting}
                              data-testid="herodraft-choice-radiant"
                            >
                              {isSubmitting ? "..." : "Radiant"}
                            </Button>
                            <Button
                              onClick={() => setPendingChoice({ type: "side", value: "dire" })}
                              disabled={isSubmitting}
                              data-testid="herodraft-choice-dire"
                            >
                              {isSubmitting ? "..." : "Dire"}
                            </Button>
                          </div>
                        </div>
                      )
                    ) : myTeam && rollWinnerTeam?.is_first_pick === null && rollWinnerTeam?.is_radiant === null ? (
                      // Loser waits until winner makes their first choice
                      <p data-testid="herodraft-waiting-for-winner">
                        Waiting for {rollWinnerTeam?.captain ? DisplayName(rollWinnerTeam.captain) : 'winner'} to choose...
                      </p>
                    ) : myTeam ? (
                      <div className="space-y-2" data-testid="herodraft-loser-choices">
                        <p>Choose the remaining option:</p>
                        <div className="flex gap-4 justify-center" data-testid="herodraft-remaining-choice-buttons">
                          {rollWinnerTeam?.is_first_pick === null && (
                            <>
                              <Button
                                onClick={() =>
                                  setPendingChoice({ type: "pick_order", value: "first" })
                                }
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-first-pick"
                              >
                                {isSubmitting ? "..." : "First Pick"}
                              </Button>
                              <Button
                                onClick={() =>
                                  setPendingChoice({ type: "pick_order", value: "second" })
                                }
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-second-pick"
                              >
                                {isSubmitting ? "..." : "Second Pick"}
                              </Button>
                            </>
                          )}
                          {rollWinnerTeam?.is_radiant === null && (
                            <>
                              <Button
                                onClick={() => setPendingChoice({ type: "side", value: "radiant" })}
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-radiant"
                              >
                                {isSubmitting ? "..." : "Radiant"}
                              </Button>
                              <Button
                                onClick={() => setPendingChoice({ type: "side", value: "dire" })}
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-dire"
                              >
                                {isSubmitting ? "..." : "Dire"}
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p data-testid="herodraft-spectating">Spectating...</p>
                    )}
                  </div>
                </div>
              )}

              {/* Completed draft view - full screen display of teams (when not viewing full draft) */}
              {draft.state === "completed" && !showFullDraft && (
                <CompletedDraftView
                  draft={draft}
                  onViewFullDraft={() => setShowFullDraft(true)}
                />
              )}

              {/* Small screen message - shown below sm breakpoint for in-progress drafts */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "resuming") && (
                <div className="flex-1 flex sm:hidden items-start justify-start p-6" data-testid="herodraft-small-screen-message">
                  <div className="text-left space-y-2 max-w-xs">
                    <div className="text-3xl">🚧</div>
                    <h2 className="text-lg font-bold text-white">Mobile View Under Construction</h2>
                    <p className="text-gray-400 text-sm">
                      The mobile draft view is coming soon. Please view this on a tablet or desktop browser for now.
                    </p>
                  </div>
                </div>
              )}

              {/* Main draft area - hidden on small screens, side-by-side on sm+ */}
              {/* Shows during drafting/paused/resuming, OR when viewing full draft in completed state */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "resuming" || (draft.state === "completed" && showFullDraft)) && (
                <div className="flex-1 hidden sm:flex flex-row overflow-hidden" data-testid="herodraft-main-area">
                  {/* Hero Grid - 50% sm/md, 58% lg, 80% xl */}
                  <div className="basis-1/2 md:basis-1/2 lg:basis-7/12 xl:basis-4/5 h-full min-w-0 overflow-hidden" data-testid="herodraft-hero-grid-container">
                    <HeroGrid
                      onHeroClick={handleHeroClick}
                      disabled={!isMyTurn || draft.state !== "drafting"}
                      showActionButton={isCaptain ?? false}
                      currentAction={currentAction}
                      isMyTurn={isMyTurn}
                    />
                  </div>

                  {/* Draft Panel - 50% sm/md, 42% lg, 20% xl */}
                  <div className="basis-1/2 md:basis-1/2 lg:basis-5/12 xl:basis-1/5 h-full min-w-0 overflow-auto border-l border-gray-800" data-testid="herodraft-panel-container">
                    <DraftPanel
                      draft={draft}
                      currentRound={tick?.current_round ?? null}
                    />
                  </div>
                </div>
              )}

              {/* Bottom toolbar with chat and controls */}
              <div className="h-12 sm:h-14 md:h-16 shrink-0 border-t border-gray-800 flex items-center px-2 sm:px-4 gap-2 sm:gap-4" data-testid="herodraft-bottom-toolbar">
                {/* Chat input - hidden on small screens */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="hidden md:flex flex-1 items-center gap-2">
                      <Input
                        placeholder="Team chat..."
                        value={chatMessage}
                        onChange={(e) => setChatMessage(e.target.value)}
                        disabled
                        className="flex-1 bg-gray-800 border-gray-700 text-white placeholder:text-gray-500 cursor-not-allowed"
                        data-testid="herodraft-chat-input"
                      />
                      <Button
                        variant="secondary"
                        size="icon"
                        disabled
                        className="shrink-0"
                        data-testid="herodraft-chat-send"
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>Under Construction</TooltipContent>
                </Tooltip>

                {/* Spacer on small screens */}
                <div className="flex-1 md:hidden" />

                {/* Right side controls */}
                <div className="flex items-center gap-1 sm:gap-2 shrink-0">
                  {/* Pause button - shown during drafting for captains/staff */}
                  {draft.state === "drafting" && (isCaptain || currentUser?.is_staff) && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handlePause}
                          disabled={isSubmitting}
                          data-testid="herodraft-pause-btn"
                          className="flex items-center text-xs sm:text-sm border-yellow-500 text-yellow-500 hover:bg-yellow-500/20"
                        >
                          <Pause className="h-3 w-3 sm:h-4 sm:w-4 sm:mr-2" />
                          <span className="hidden sm:inline">Pause</span>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Pause the draft</TooltipContent>
                    </Tooltip>
                  )}
                  {/* View Teams button - shown when viewing full draft on completed state */}
                  {draft.state === "completed" && showFullDraft && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowFullDraft(false)}
                      data-testid="herodraft-view-teams-btn"
                      className="flex items-center text-xs sm:text-sm"
                    >
                      <Users className="h-3 w-3 sm:h-4 sm:w-4 sm:mr-2" />
                      <span className="hidden sm:inline">View Teams</span>
                    </Button>
                  )}
                  <HistoryButton
                    data-testid="herodraft-history-btn"
                    onClick={() => setShowHistoryModal(true)}
                    eventCount={draft.rounds.filter(r => r.state === "completed").length}
                    tooltipText="Draft History"
                    size="sm"
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleClose}
                    data-testid="herodraft-close-btn"
                    className="flex items-center justify-start text-xs sm:text-sm"
                  >
                    <ArrowLeft className="h-3 w-3 sm:h-4 sm:w-4 sm:mr-2" />
                    <span className="hidden sm:inline">Back to Bracket</span>
                  </Button>
                </div>
              </div>

              {/* Paused/Resuming overlay - shows during pause and countdown */}
              {(() => {
                // Use local countdown (not server ticks) to avoid latency issues
                const isResuming = draft.state === "resuming";
                const countdownValue = resumeCountdown;
                const showOverlay = draft.state === "paused" || isResuming || resumeCountdown !== null;

                // Check if both captains are connected
                const allCaptainsConnected = draft.draft_teams.every(t => t.is_connected);
                // Check if user can resume (captain or staff)
                const canResume = isCaptain || currentUser?.is_staff;
                // Get pause reason message
                const isManualPause = draft.is_manual_pause;

                return showOverlay && (
                  <div className="absolute inset-0 bg-black/70 flex items-center justify-center" data-testid="herodraft-paused-overlay">
                    <div className="text-center space-y-4">
                      {(countdownValue !== null && countdownValue > 0) ? (
                        <>
                          <h2 className="text-3xl font-bold text-green-400" data-testid="herodraft-countdown-title">
                            Resuming in {countdownValue}...
                          </h2>
                          <p className="text-muted-foreground" data-testid="herodraft-countdown-message">
                            Get ready!
                          </p>
                        </>
                      ) : (
                        <>
                          <h2 className="text-3xl font-bold text-yellow-400" data-testid="herodraft-paused-title">
                            Draft Paused
                          </h2>
                          <p className="text-muted-foreground" data-testid="herodraft-paused-message">
                            {isManualPause
                              ? "Paused by captain or staff"
                              : allCaptainsConnected
                                ? "Click Resume to continue"
                                : "Waiting for captain to reconnect..."}
                          </p>
                          <div className="flex flex-col gap-2 items-center">
                            {canResume && allCaptainsConnected && (
                              <Button
                                variant="default"
                                onClick={handleResume}
                                disabled={isSubmitting}
                                className="bg-green-600 hover:bg-green-700 text-white"
                                data-testid="herodraft-resume-btn"
                              >
                                <Play className="h-4 w-4 mr-2" />
                                {isSubmitting ? "Resuming..." : "Resume Draft"}
                              </Button>
                            )}
                            {!allCaptainsConnected && (
                              <Button
                                variant="outline"
                                onClick={reconnect}
                                className="text-white border-yellow-400 hover:bg-yellow-400/20"
                                data-testid="herodraft-reconnect-btn"
                              >
                                Reconnect
                              </Button>
                            )}
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={handleClose}
                              data-testid="herodraft-paused-close-btn"
                            >
                              <ArrowLeft className="h-4 w-4 mr-2" />
                              Back to Bracket
                            </Button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Kicked overlay - shows when connection was replaced by another tab */}
              {wasKicked && (
                <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-50" data-testid="herodraft-kicked-overlay">
                  <div className="text-center space-y-4 max-w-md px-6">
                    <h2 className="text-2xl font-bold text-orange-400" data-testid="herodraft-kicked-title">
                      Session Replaced
                    </h2>
                    <p className="text-gray-300" data-testid="herodraft-kicked-message">
                      Another browser tab has taken over this draft session.
                      Refresh this page to take control back.
                    </p>
                    <div className="flex flex-col gap-2 items-center pt-2">
                      <Button
                        variant="default"
                        onClick={() => window.location.reload()}
                        className="bg-orange-500 hover:bg-orange-600 text-white"
                        data-testid="herodraft-kicked-refresh-btn"
                      >
                        Refresh Page
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleClose}
                        data-testid="herodraft-kicked-close-btn"
                      >
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Bracket
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {/* Connection status */}
              {!isConnected && !wasKicked && (
                <div className="absolute top-2 right-2 bg-red-500/80 text-white px-3 py-2 rounded text-sm flex items-center gap-2" data-testid="herodraft-reconnecting">
                  <span>{connectionError || "Reconnecting..."}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={reconnect}
                    className="h-6 px-2 text-xs hover:bg-red-600"
                    data-testid="herodraft-reconnect-inline-btn"
                  >
                    Retry
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Draft history modal */}
      {draft && (
        <HeroDraftHistoryModal
          open={showHistoryModal}
          onOpenChange={setShowHistoryModal}
          rounds={draft.rounds}
          draftTeams={draft.draft_teams}
        />
      )}

      {/* Confirm pick dialog */}
      <AlertDialog
        open={confirmHeroId !== null}
        onOpenChange={() => {
          setConfirmHeroId(null);
          setSelectedHeroId(null);
        }}
      >
        <AlertDialogContent data-testid="herodraft-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle data-testid="herodraft-confirm-title">
              {currentAction === "ban" ? "Ban" : "Pick"} this hero?
            </AlertDialogTitle>
            <AlertDialogDescription data-testid="herodraft-confirm-description">
              Are you sure you want to {currentAction} this hero?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmitting} data-testid="herodraft-confirm-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmPick} disabled={isSubmitting} data-testid="herodraft-confirm-submit">
              {isSubmitting
                ? "Submitting..."
                : `Confirm ${currentAction === "ban" ? "Ban" : "Pick"}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirm choice dialog (for pick order / side selection) */}
      <AlertDialog
        open={pendingChoice !== null}
        onOpenChange={() => setPendingChoice(null)}
      >
        <AlertDialogContent data-testid="herodraft-confirm-choice-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle data-testid="herodraft-confirm-choice-title">
              Confirm your choice
            </AlertDialogTitle>
            <AlertDialogDescription data-testid="herodraft-confirm-choice-description">
              Are you sure you want to choose{" "}
              <span className="font-semibold text-white">
                {pendingChoice ? getChoiceLabel(pendingChoice.type, pendingChoice.value) : ""}
              </span>
              ? This choice cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmitting} data-testid="herodraft-confirm-choice-cancel">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmPendingChoice}
              disabled={isSubmitting}
              data-testid="herodraft-confirm-choice-submit"
            >
              {isSubmitting ? "Submitting..." : "Confirm"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
