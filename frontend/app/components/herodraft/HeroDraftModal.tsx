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
import type { HeroDraft } from "./types";
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

  const handleEvent = useCallback((eventType: string, _draftTeam: number | null) => {
    switch (eventType) {
      case "captain_ready":
        toast.info("Captain is ready");
        break;
      case "roll_result":
        toast.success("Coin flip complete!");
        break;
      case "hero_selected":
        toast.info("Hero selected");
        break;
      case "draft_completed":
        toast.success("Draft completed!");
        break;
    }
  }, []);

  const { isConnected } = useHeroDraftWebSocket({
    draftId,
    enabled: open,  // Only connect when modal is open
    onStateUpdate: handleStateUpdate,
    onTick: handleTick,
    onEvent: handleEvent,
  });

  const handleHeroClick = (heroId: number) => {
    if (!draft || !currentUser?.pk) return;

    const myTeam = draft.draft_teams.find((t) => t.captain?.pk === currentUser.pk);
    if (!myTeam) return;

    // Find current round from rounds array using current_round index
    const currentRound = draft.current_round !== null ? draft.rounds[draft.current_round] : null;
    if (!currentRound || currentRound.draft_team !== myTeam.id) {
      toast.error("It's not your turn");
      return;
    }

    setConfirmHeroId(heroId);
  };

  const handleConfirmPick = async () => {
    if (!confirmHeroId || !draft || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const updated = await submitPick(draft.id, confirmHeroId);
      setDraft(updated);
      setConfirmHeroId(null);
      setSelectedHeroId(null);
    } catch (error: unknown) {
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
      const updated = await setReady(draft.id);
      setDraft(updated);
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
      const updated = await triggerRoll(draft.id);
      setDraft(updated);
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
      const updated = await submitChoice(
        draft.id,
        choiceType,
        value as "first" | "second" | "radiant" | "dire"
      );
      setDraft(updated);
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
          className="!fixed !inset-0 !translate-x-0 !translate-y-0 !top-0 !left-0 !max-w-none !sm:max-w-none !w-screen !h-screen !p-0 !gap-0 !rounded-none !border-0 bg-gray-900"
          showCloseButton={false}
          data-testid="herodraft-modal"
        >
          <VisuallyHidden>
            <DialogTitle>Hero Draft</DialogTitle>
            <DialogDescription>Captain's Mode hero draft interface</DialogDescription>
          </VisuallyHidden>
          {draft && (
            <div className="flex flex-col h-full bg-gray-900" data-testid="herodraft-container">
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

              {/* Main draft area - mobile: stacked, desktop: side-by-side */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "completed") && (
                <div className="flex-1 flex flex-col lg:flex-row overflow-hidden" data-testid="herodraft-main-area">
                  {/* Hero Grid - full width on mobile, flex-1 on desktop */}
                  <div className="flex-1 min-h-0 border-b lg:border-b-0 lg:border-r border-gray-800" data-testid="herodraft-hero-grid-container">
                    <HeroGrid
                      onHeroClick={handleHeroClick}
                      disabled={!isMyTurn || draft.state !== "drafting"}
                      showActionButton={isCaptain ?? false}
                    />
                  </div>

                  {/* Draft Panel - full width on mobile, fixed width on desktop */}
                  <div className="h-48 lg:h-auto lg:w-80 overflow-auto" data-testid="herodraft-panel-container">
                    <DraftPanel
                      draft={draft}
                      currentRound={tick?.current_round ?? null}
                    />
                  </div>
                </div>
              )}

              {/* Bottom toolbar with chat and controls */}
              <div className="h-16 border-t border-gray-800 flex items-center px-4 gap-4" data-testid="herodraft-bottom-toolbar">
                {/* Chat input - left side, takes remaining space */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="flex-1 flex items-center gap-2">
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

                {/* Right side controls */}
                <div className="flex items-center gap-2">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowHistoryModal(true)}
                        className="text-white border-gray-600 hover:bg-gray-800"
                        data-testid="herodraft-history-btn"
                      >
                        <History className="h-4 w-4 mr-2" />
                        History
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Draft Events</TooltipContent>
                  </Tooltip>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={onClose}
                    data-testid="herodraft-close-btn"
                    className="flex items-center justify-start"
                  >
                    <X className="h-4 w-4 mr-2" />
                    Close
                  </Button>
                </div>
              </div>

              {/* Paused overlay */}
              {draft.state === "paused" && (
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center" data-testid="herodraft-paused-overlay">
                  <div className="text-center">
                    <h2 className="text-3xl font-bold text-yellow-400" data-testid="herodraft-paused-title">
                      Draft Paused
                    </h2>
                    <p className="text-muted-foreground" data-testid="herodraft-paused-message">
                      Waiting for captain to reconnect...
                    </p>
                  </div>
                </div>
              )}

              {/* Connection status */}
              {!isConnected && (
                <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-sm" data-testid="herodraft-reconnecting">
                  Reconnecting...
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
