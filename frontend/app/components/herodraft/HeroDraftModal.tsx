// frontend/app/components/herodraft/HeroDraftModal.tsx
import { useCallback, useState, useMemo } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "~/components/ui/dialog";
import { VisuallyHidden } from "~/components/ui/visually-hidden";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { useHeroDraftStore } from "~/store/heroDraftStore";
import { useHeroDraftWebSocket } from "./hooks/useHeroDraftWebSocket";
import { useUserStore } from "~/store/userStore";
import { DraftTopBar } from "./DraftTopBar";
import { HeroGrid } from "./HeroGrid";
import { DraftPanel } from "./DraftPanel";
import { HeroDraftHistoryModal } from "./HeroDraftHistoryModal";
import { submitPick, setReady, triggerRoll, submitChoice } from "./api";
import type { HeroDraft, HeroDraftEvent } from "./types";
import { heroes } from "dotaconstants";
import { DisplayName } from "~/components/user/avatar";
import { X, Send, History } from "lucide-react";
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
  const { currentUser } = useUserStore();
  // Use selectors to prevent re-renders when unrelated state changes
  const draft = useHeroDraftStore((state) => state.draft);
  const tick = useHeroDraftStore((state) => state.tick);
  const setDraft = useHeroDraftStore((state) => state.setDraft);
  const setTick = useHeroDraftStore((state) => state.setTick);
  const setSelectedHeroId = useHeroDraftStore((state) => state.setSelectedHeroId);

  const [confirmHeroId, setConfirmHeroId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [chatMessage, setChatMessage] = useState("");

  const handleStateUpdate = useCallback(
    (newDraft: HeroDraft) => {
      setDraft(newDraft);
    },
    [setDraft]
  );

  const handleTick = useCallback(
    (newTick: Parameters<typeof setTick>[0]) => {
      setTick(newTick);
    },
    [setTick]
  );

  const handleEvent = useCallback((event: HeroDraftEvent) => {
    console.log("[HeroDraftModal] handleEvent:", event.event_type, event);

    // Get hero name helper
    const getHeroName = (heroId: number | undefined): string => {
      if (!heroId) return "Unknown Hero";
      const hero = Object.values(heroes).find((h: { id: number }) => h.id === heroId);
      return (hero as { localized_name: string } | undefined)?.localized_name ?? `Hero ${heroId}`;
    };

    // Get captain display name
    const draftTeam = event.draft_team;
    const captainName = draftTeam?.captain
      ? (draftTeam.captain.nickname || draftTeam.captain.username)
      : "Unknown";

    switch (event.event_type) {
      case "captain_ready":
        toast.info(`${captainName} is ready`);
        break;
      case "captain_connected":
        toast.success(`${captainName} connected`);
        break;
      case "captain_disconnected":
        toast.warning(`${captainName} disconnected`);
        break;
      case "draft_paused":
        toast.warning("Draft paused - waiting for captain to reconnect");
        break;
      case "draft_resumed":
        toast.success("Draft resumed - all captains connected");
        break;
      case "roll_result":
        toast.success(`${captainName} won the coin flip!`);
        break;
      case "hero_selected": {
        // Get hero_id and action_type from metadata
        const heroId = event.metadata?.hero_id;
        const actionType = event.metadata?.action_type;
        const heroName = getHeroName(heroId);
        const action = actionType === "ban" ? "banned" : "picked";
        toast.info(`${captainName} ${action} ${heroName}`);
        break;
      }
      case "draft_completed":
        toast.success("Draft completed!");
        break;
    }
  }, []);

  const { isConnected, connectionError, reconnect } = useHeroDraftWebSocket({
    draftId,
    enabled: open,  // Only connect when modal is open
    onStateUpdate: handleStateUpdate,
    onTick: handleTick,
    onEvent: handleEvent,
  });

  const handleHeroClick = (heroId: number) => {
    console.log("[HeroDraftModal] handleHeroClick:", {
      heroId,
      draft_state: draft?.state,
      draft_current_round: draft?.current_round,
      currentUser_pk: currentUser?.pk,
    });

    if (!draft || !currentUser?.pk) {
      console.log("[HeroDraftModal] handleHeroClick - early return: no draft or user");
      return;
    }

    const myTeam = draft.draft_teams.find((t) => t.captain?.pk === currentUser.pk);
    console.log("[HeroDraftModal] handleHeroClick:", {
      myTeam_id: myTeam?.id,
      myTeam_captain: myTeam?.captain?.username,
    });

    if (!myTeam) {
      console.log("[HeroDraftModal] handleHeroClick - early return: not a captain");
      return;
    }

    // Find current round from rounds array using current_round index
    const currentRound = draft.current_round !== null ? draft.rounds[draft.current_round] : null;
    console.log("[HeroDraftModal] handleHeroClick:", {
      currentRound_number: currentRound?.round_number,
      currentRound_draft_team: currentRound?.draft_team,
      currentRound_state: currentRound?.state,
      currentRound_action_type: currentRound?.action_type,
      isMyTurn: currentRound?.draft_team === myTeam.id,
    });

    if (!currentRound || currentRound.draft_team !== myTeam.id) {
      console.log("[HeroDraftModal] handleHeroClick - not your turn!");
      toast.error("It's not your turn");
      return;
    }

    console.log("[HeroDraftModal] handleHeroClick - setting confirmHeroId:", heroId);
    setConfirmHeroId(heroId);
  };

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

  // Find current round from rounds array
  const currentRoundData = draft && draft.current_round !== null
    ? draft.rounds[draft.current_round]
    : null;

  const isMyTurn = currentRoundData
    ? draft?.draft_teams.find((t) => t.id === currentRoundData.draft_team)
        ?.captain?.pk === currentUser?.pk
    : false;

  const isCaptain = draft?.draft_teams.some((t) => t.captain?.pk === currentUser?.pk);
  const myTeam = draft?.draft_teams.find((t) => t.captain?.pk === currentUser?.pk);
  // roll_winner is already the full DraftTeam object from the backend
  const rollWinnerTeam = draft?.roll_winner ?? null;

  const currentAction = currentRoundData?.action_type;

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
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
                      <div className="space-y-2" data-testid="herodraft-winner-choices">
                        <p>Choose your preference:</p>
                        <div className="flex gap-4 justify-center" data-testid="herodraft-choice-buttons">
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "first")}
                            disabled={isSubmitting}
                            data-testid="herodraft-choice-first-pick"
                          >
                            {isSubmitting ? "..." : "First Pick"}
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "second")}
                            disabled={isSubmitting}
                            data-testid="herodraft-choice-second-pick"
                          >
                            {isSubmitting ? "..." : "Second Pick"}
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "radiant")}
                            disabled={isSubmitting}
                            data-testid="herodraft-choice-radiant"
                          >
                            {isSubmitting ? "..." : "Radiant"}
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "dire")}
                            disabled={isSubmitting}
                            data-testid="herodraft-choice-dire"
                          >
                            {isSubmitting ? "..." : "Dire"}
                          </Button>
                        </div>
                      </div>
                    ) : myTeam && !rollWinnerTeam ? (
                      <p data-testid="herodraft-waiting-for-winner">Waiting for roll winner to choose...</p>
                    ) : myTeam ? (
                      <div className="space-y-2" data-testid="herodraft-loser-choices">
                        <p>Choose the remaining option:</p>
                        <div className="flex gap-4 justify-center" data-testid="herodraft-remaining-choice-buttons">
                          {rollWinnerTeam?.is_first_pick === null && (
                            <>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "first")
                                }
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-first-pick"
                              >
                                {isSubmitting ? "..." : "First Pick"}
                              </Button>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "second")
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
                                onClick={() => handleChoiceSubmit("side", "radiant")}
                                disabled={isSubmitting}
                                data-testid="herodraft-remaining-radiant"
                              >
                                {isSubmitting ? "..." : "Radiant"}
                              </Button>
                              <Button
                                onClick={() => handleChoiceSubmit("side", "dire")}
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

              {/* Small screen message - shown below sm breakpoint */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "completed") && (
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
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "completed") && (
                <div className="flex-1 hidden sm:flex flex-row overflow-hidden" data-testid="herodraft-main-area">
                  {/* Hero Grid - 50% sm/md, 58% lg, 80% xl */}
                  <div className="basis-1/2 md:basis-1/2 lg:basis-7/12 xl:basis-4/5 h-full min-w-0 overflow-hidden" data-testid="herodraft-hero-grid-container">
                    <HeroGrid
                      onHeroClick={handleHeroClick}
                      disabled={!isMyTurn || draft.state !== "drafting"}
                      showActionButton={isCaptain ?? false}
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
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowHistoryModal(true)}
                        className="text-white border-gray-600 hover:bg-gray-800 text-xs sm:text-sm"
                        data-testid="herodraft-history-btn"
                      >
                        <History className="h-3 w-3 sm:h-4 sm:w-4 sm:mr-2" />
                        <span className="hidden sm:inline">History</span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Draft Events</TooltipContent>
                  </Tooltip>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={onClose}
                    data-testid="herodraft-close-btn"
                    className="flex items-center justify-start text-xs sm:text-sm"
                  >
                    <X className="h-3 w-3 sm:h-4 sm:w-4 sm:mr-2" />
                    <span className="hidden sm:inline">Close</span>
                  </Button>
                </div>
              </div>

              {/* Paused overlay */}
              {draft.state === "paused" && (
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center" data-testid="herodraft-paused-overlay">
                  <div className="text-center space-y-4">
                    <h2 className="text-3xl font-bold text-yellow-400" data-testid="herodraft-paused-title">
                      Draft Paused
                    </h2>
                    <p className="text-muted-foreground" data-testid="herodraft-paused-message">
                      Waiting for captain to reconnect...
                    </p>
                    <Button
                      variant="outline"
                      onClick={reconnect}
                      className="text-white border-yellow-400 hover:bg-yellow-400/20"
                      data-testid="herodraft-reconnect-btn"
                    >
                      Reconnect
                    </Button>
                  </div>
                </div>
              )}

              {/* Connection status */}
              {!isConnected && (
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
        onOpenChange={() => setConfirmHeroId(null)}
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
    </>
  );
}
