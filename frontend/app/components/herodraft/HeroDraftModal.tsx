// frontend/app/components/herodraft/HeroDraftModal.tsx
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent } from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { useHeroDraftStore } from "~/store/heroDraftStore";
import { useHeroDraftWebSocket } from "./hooks/useHeroDraftWebSocket";
import { useUserStore } from "~/store/userStore";
import { DraftTopBar } from "./DraftTopBar";
import { HeroGrid } from "./HeroGrid";
import { DraftPanel } from "./DraftPanel";
import { submitPick, setReady, triggerRoll, submitChoice } from "./api";
import type { HeroDraft } from "./types";
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
  const { draft, tick, setDraft, setTick, setSelectedHeroId } =
    useHeroDraftStore();

  const [confirmHeroId, setConfirmHeroId] = useState<number | null>(null);

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
    onStateUpdate: handleStateUpdate,
    onTick: handleTick,
    onEvent: handleEvent,
  });

  const handleHeroClick = (heroId: number) => {
    if (!draft || !currentUser?.pk) return;

    const myTeam = draft.draft_teams.find((t) => t.captain?.id === currentUser.pk);
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
    if (!confirmHeroId || !draft) return;

    try {
      const updated = await submitPick(draft.id, confirmHeroId);
      setDraft(updated);
      setConfirmHeroId(null);
      setSelectedHeroId(null);
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to submit pick");
    }
  };

  const handleReady = async () => {
    if (!draft) return;
    try {
      const updated = await setReady(draft.id);
      setDraft(updated);
      toast.success("You are ready!");
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to set ready");
    }
  };

  const handleTriggerRoll = async () => {
    if (!draft) return;
    try {
      const updated = await triggerRoll(draft.id);
      setDraft(updated);
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { error?: string } } };
      toast.error(axiosError.response?.data?.error || "Failed to trigger roll");
    }
  };

  const handleChoiceSubmit = async (
    choiceType: "pick_order" | "side",
    value: string
  ) => {
    if (!draft) return;
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
    }
  };

  // Find current round from rounds array
  const currentRoundData = draft && draft.current_round !== null
    ? draft.rounds[draft.current_round]
    : null;

  const isMyTurn = currentRoundData
    ? draft?.draft_teams.find((t) => t.id === currentRoundData.draft_team)
        ?.captain?.id === currentUser?.pk
    : false;

  const isCaptain = draft?.draft_teams.some((t) => t.captain?.id === currentUser?.pk);
  const myTeam = draft?.draft_teams.find((t) => t.captain?.id === currentUser?.pk);
  const rollWinnerTeam = draft?.roll_winner
    ? draft.draft_teams.find(t => t.id === draft.roll_winner)
    : null;

  const currentAction = currentRoundData?.action_type;

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-[100vw] max-h-[100vh] w-screen h-screen p-0 gap-0">
          {draft && (
            <div className="flex flex-col h-full bg-gray-900">
              {/* Top Bar */}
              <DraftTopBar draft={draft} tick={tick} />

              {/* Pre-draft phases */}
              {draft.state === "waiting_for_captains" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">Waiting for Captains</h2>
                    <div className="flex gap-8">
                      {draft.draft_teams.map((team) => (
                        <div key={team.id} className="text-center">
                          <p className="font-semibold">
                            {team.captain?.nickname || team.captain?.username}
                          </p>
                          <p
                            className={
                              team.is_ready ? "text-green-400" : "text-yellow-400"
                            }
                          >
                            {team.is_ready ? "Ready" : "Not Ready"}
                          </p>
                        </div>
                      ))}
                    </div>
                    {isCaptain && !myTeam?.is_ready && (
                      <Button onClick={handleReady}>Ready</Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "rolling" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">Both Captains Ready!</h2>
                    <p>Click to trigger the coin flip</p>
                    {isCaptain && (
                      <Button onClick={handleTriggerRoll}>Flip Coin</Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "choosing" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">
                      {rollWinnerTeam?.captain?.username} won the flip!
                    </h2>
                    {rollWinnerTeam?.id === myTeam?.id ? (
                      <div className="space-y-2">
                        <p>Choose your preference:</p>
                        <div className="flex gap-4 justify-center">
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "first")}
                          >
                            First Pick
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "second")}
                          >
                            Second Pick
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "radiant")}
                          >
                            Radiant
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "dire")}
                          >
                            Dire
                          </Button>
                        </div>
                      </div>
                    ) : myTeam && !rollWinnerTeam ? (
                      <p>Waiting for roll winner to choose...</p>
                    ) : myTeam ? (
                      <div className="space-y-2">
                        <p>Choose the remaining option:</p>
                        <div className="flex gap-4 justify-center">
                          {rollWinnerTeam?.is_first_pick === null && (
                            <>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "first")
                                }
                              >
                                First Pick
                              </Button>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "second")
                                }
                              >
                                Second Pick
                              </Button>
                            </>
                          )}
                          {rollWinnerTeam?.is_radiant === null && (
                            <>
                              <Button
                                onClick={() => handleChoiceSubmit("side", "radiant")}
                              >
                                Radiant
                              </Button>
                              <Button
                                onClick={() => handleChoiceSubmit("side", "dire")}
                              >
                                Dire
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p>Spectating...</p>
                    )}
                  </div>
                </div>
              )}

              {/* Main draft area */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "completed") && (
                <div className="flex-1 flex overflow-hidden">
                  {/* Left: Hero Grid */}
                  <div className="flex-1 border-r border-gray-800">
                    <HeroGrid
                      onHeroClick={handleHeroClick}
                      disabled={!isMyTurn || draft.state !== "drafting"}
                      showActionButton={isCaptain ?? false}
                    />
                  </div>

                  {/* Right: Draft Panel */}
                  <div className="w-80">
                    <DraftPanel
                      draft={draft}
                      currentRound={tick?.current_round ?? null}
                    />
                  </div>
                </div>
              )}

              {/* Bottom: Chat placeholder */}
              <div className="h-20 border-t border-gray-800 flex items-center justify-center text-muted-foreground">
                <span>Team Chat - Under Construction</span>
              </div>

              {/* Paused overlay */}
              {draft.state === "paused" && (
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
                  <div className="text-center">
                    <h2 className="text-3xl font-bold text-yellow-400">
                      Draft Paused
                    </h2>
                    <p className="text-muted-foreground">
                      Waiting for captain to reconnect...
                    </p>
                  </div>
                </div>
              )}

              {/* Connection status */}
              {!isConnected && (
                <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-sm">
                  Reconnecting...
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirm pick dialog */}
      <AlertDialog
        open={confirmHeroId !== null}
        onOpenChange={() => setConfirmHeroId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {currentAction === "ban" ? "Ban" : "Pick"} this hero?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to {currentAction} this hero?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmPick}>
              Confirm {currentAction === "ban" ? "Ban" : "Pick"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
