import { useState, useEffect, type FormEvent } from 'react';
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
import type { UserType } from '~/index';
import { DisplayName } from '~/components/user/avatar';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { choosePlayerHook } from '../hooks/choosePlayerHook';
import { TieResolutionOverlay } from '../TieResolutionOverlay';
import type { TieResolution } from '../types';
const log = getLogger('pickPlayerButton');

export const ChoosePlayerButton: React.FC<{
  user: UserType;
}> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);
  const currentUser = useUserStore((state) => state.currentUser);

  const setTournament = useUserStore((state) => state.setTournament);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);
  const isStaff = useUserStore((state) => state.isStaff);

  const setDraft = useUserStore((state) => state.setDraft);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const autoRefreshDraft = useUserStore((state) => state.autoRefreshDraft);

  const [tieResolution, setTieResolution] = useState<TieResolution | null>(
    null,
  );
  const [showTieOverlay, setShowTieOverlay] = useState(false);

  // Check if current user is logged in
  const isLoggedIn = currentUser?.pk != null;

  // Check if current user is a captain of any team in this tournament
  const isAnyCaptain = tournament?.teams?.some(
    (team) => team.captain?.pk === currentUser?.pk
  );

  // Check if current user is the captain for this round
  // Must check that both currentUser and captain exist with valid pks to avoid undefined === undefined
  const isCaptainForRound =
    currentUser?.pk != null &&
    curDraftRound?.captain?.pk != null &&
    currentUser.pk === curDraftRound.captain.pk;
  const canPick = isStaff() || isCaptainForRound;
  const pickAlreadyMade = !!curDraftRound?.choice;

  useEffect(() => {}, [tournament.draft, tournament.teams]);

  const handleChange = async (e: FormEvent) => {
    log.debug('ChoosePlayerButton: Tournament', {
      tournament,
    });

    // choosePlayerHook handles all state updates in its success callback
    // No need for separate refreshDraftHook call - it would use stale data
    await choosePlayerHook({
      tournament,
      setTournament,
      player: user,
      curDraftRound,
      setCurDraftRound,
      setDraft,
      setDraftIndex,
      onTieResolution: (resolution) => {
        setTieResolution(resolution);
        setShowTieOverlay(true);
      },
      autoRefreshDraft: autoRefreshDraft || undefined,
    });

    log.debug('updateDraftRound', {
      user: DisplayName(user),
      draft_round: curDraftRound.pk,
      draft: draft,
    });
  };

  // If pick already made for this round, show disabled button
  if (pickAlreadyMade) {
    return (
      <Button disabled variant="outline" size="sm" className="text-xs px-2">
        Done
      </Button>
    );
  }

  // If user can't pick (not staff and not captain for this round)
  if (!canPick) {
    // Not logged in
    if (!isLoggedIn) {
      return (
        <Button disabled variant="ghost" size="sm" className="text-xs px-2 text-muted-foreground">
          Login...
        </Button>
      );
    }
    // User is a captain but not their turn
    if (isAnyCaptain) {
      return (
        <Button disabled variant="ghost" size="sm" className="text-xs px-2 text-muted-foreground">
          Not your turn
        </Button>
      );
    }
    // Regular user watching
    return (
      <Button disabled variant="ghost" size="sm" className="text-xs px-2 text-muted-foreground">
        Waiting...
      </Button>
    );
  }

  return (
    <>
      <div data-testid="available-player">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="sm" className="text-xs px-2">Pick</Button>
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
      {showTieOverlay && tieResolution && (
        <TieResolutionOverlay
          tieResolution={tieResolution}
          onDismiss={() => {
            setShowTieOverlay(false);
            setTieResolution(null);
          }}
        />
      )}
    </>
  );
};
