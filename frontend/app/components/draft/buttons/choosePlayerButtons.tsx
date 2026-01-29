import React, { useState, useMemo, type FormEvent } from 'react';
import { toast } from 'sonner';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '~/components/ui/alert-dialog';
import { Button } from '~/components/ui/button';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';
import type { UserType, TournamentType } from '~/index';
import { DisplayName } from '~/components/user/avatar';
import { PickPlayerForRound } from '~/components/api/api';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import { TieResolutionOverlay } from '../TieResolutionOverlay';
import type { TieResolution } from '../types';
const log = getLogger('pickPlayerButton');

export const ChoosePlayerButton: React.FC<{
  user: UserType;
}> = ({ user }) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);

  // Only subscribe to draft_rounds (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  const loadDraft = useTeamDraftStore((state) => state.loadDraft);
  const setTieResolution = useTeamDraftStore((state) => state.setTieResolution);
  const loadAll = useTournamentDataStore((state) => state.loadAll);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);

  const [localTieResolution, setLocalTieResolution] = useState<TieResolution | null>(null);
  const [showTieOverlay, setShowTieOverlay] = useState(false);

  // Check if current user is the captain for this round
  const isCaptainForRound = currentUser?.pk === curDraftRound?.captain?.pk;
  const canPick = isStaff() || isCaptainForRound;
  const pickAlreadyMade = !!curDraftRound?.choice;

  const handleChange = async (e: FormEvent) => {
    if (!curDraftRound?.pk || !user?.pk) {
      log.error('Missing draft round or user');
      return;
    }

    log.debug('ChoosePlayerButton: Picking player', { user: DisplayName(user) });

    try {
      const data = await toast.promise(
        PickPlayerForRound({
          draft_round_pk: curDraftRound.pk,
          user_pk: user.pk,
        }),
        {
          loading: `Choosing ${DisplayName(user)} for ${curDraftRound.captain ? DisplayName(curDraftRound.captain) : 'captain'} in round ${curDraftRound.pick_number}`,
          success: `Pick ${curDraftRound?.pick_number} complete!`,
          error: (err) => {
            const val = err.response?.data || 'Unknown error';
            return `Failed to pick player: ${val}`;
          },
        }
      );

      // Handle tie resolution for shuffle draft
      const responseData = data as unknown as TournamentType & { tie_resolution?: TieResolution };
      if (responseData.tie_resolution) {
        setTieResolution(responseData.tie_resolution);
        setLocalTieResolution(responseData.tie_resolution);
        setShowTieOverlay(true);
      }

      // Refresh data from server - WebSocket will also update, but this ensures consistency
      await Promise.all([loadAll(), loadDraft()]);

      log.debug('Pick complete', { user: DisplayName(user) });
    } catch (error) {
      log.error('Failed to pick player:', error);
    }
  };

  // If pick already made for this round, show disabled button
  if (pickAlreadyMade) {
    return (
      <Button disabled variant="outline">
        Pick made
      </Button>
    );
  }

  // If user can't pick (not staff and not captain for this round)
  if (!canPick) {
    const captainName = curDraftRound?.captain ? DisplayName(curDraftRound.captain) : 'captain';
    return (
      <>
        <AdminOnlyButton buttonTxt={`Waiting for ${captainName}`} />
      </>
    );
  }

  return (
    <>
      <div
        className="flex flex-row items-center gap-4"
        data-testid="available-player"
      >
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button>Pick</Button>
          </AlertDialogTrigger>
          <AlertDialogContent className="bg-green-900 border-green-700">
            <AlertDialogHeader>
              <AlertDialogTitle>Choose player {DisplayName(user)}</AlertDialogTitle>
              <AlertDialogDescription className="text-green-100">
                This will add {DisplayName(user)} to your team.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel asChild>
                <CancelButton variant="destructive">Cancel</CancelButton>
              </AlertDialogCancel>
              <AlertDialogAction asChild onClick={handleChange}>
                <ConfirmButton>Confirm Pick</ConfirmButton>
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
      {showTieOverlay && localTieResolution && (
        <TieResolutionOverlay
          tieResolution={localTieResolution}
          onDismiss={() => {
            setShowTieOverlay(false);
            setLocalTieResolution(null);
          }}
        />
      )}
    </>
  );
};
