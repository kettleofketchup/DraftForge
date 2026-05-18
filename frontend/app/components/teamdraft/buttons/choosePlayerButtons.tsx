import { useEffect, type FormEvent } from 'react';
import { useLocation } from 'react-router';
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
import { CancelButton, ConfirmButton, PrimaryButton, brandSuccessBg } from '~/components/ui/buttons';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { buildDiscordLoginUrl } from '~/components/navbar/login';
import type { UserType } from '~/index';
import { DisplayName } from '~/components/user/avatar';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { choosePlayerHook } from '../hooks/choosePlayerHook';
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
  const location = useLocation();

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
    // Not logged in — clickable AdminOnly button that kicks off Discord login
    // and returns to the current page (e.g. the tournament draft) after auth.
    if (!isLoggedIn) {
      const next = `${location.pathname}${location.search}`;
      return (
        <AdminOnlyButton
          size="sm"
          className="text-xs px-2"
          iconClassName="mr-1 h-3.5 w-3.5"
          buttonTxt="Login to Pick"
          tooltipTxt="Must be Logged In — click to sign in with Discord."
          onClick={() => {
            window.location.assign(buildDiscordLoginUrl(next));
          }}
          data-testid="pickDisabledLogin"
        />
      );
    }
    // User is a captain but not their turn
    if (isAnyCaptain) {
      return (
        <AdminOnlyButton
          size="sm"
          className="text-xs px-2"
          iconClassName="mr-1 h-3.5 w-3.5"
          buttonTxt="Not Your Turn"
          tooltipTxt="Wait for your turn — only the captain on the clock can pick."
          data-testid="pickDisabledNotYourTurn"
        />
      );
    }
    // Logged in but not a captain
    return (
      <AdminOnlyButton
        size="sm"
        className="text-xs px-2"
        iconClassName="mr-1 h-3.5 w-3.5"
        buttonTxt="Not Allowed"
        tooltipTxt="Only team captains can pick players for this draft."
        data-testid="pickDisabledWaiting"
      />
    );
  }

  return (
    <div data-testid="available-player">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <PrimaryButton size="sm" className="text-xs px-2" data-testid="pickPlayerButton">Pick</PrimaryButton>
        </AlertDialogTrigger>
        <AlertDialogContent className={`bg-green-900 ${brandSuccessBg}`}>
          <AlertDialogHeader>
            <AlertDialogTitle>Choose player {DisplayName(user)}</AlertDialogTitle>
            <AlertDialogDescription className="text-green-100">
              This will add {DisplayName(user)} to your team.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <CancelButton>Cancel</CancelButton>
            </AlertDialogCancel>
            <AlertDialogAction asChild onClick={handleChange}>
              <ConfirmButton data-testid="confirmPickButton">Confirm Pick</ConfirmButton>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
