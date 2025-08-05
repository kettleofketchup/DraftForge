import { useEffect, type FormEvent } from 'react';
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
import type { UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { choosePlayerHook } from '../hooks/choosePlayerHook';
const log = getLogger('pickPlayerButton');

export const ChoosePlayerButton: React.FC<{
  user: UserType;
}> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);

  const setTournament = useUserStore((state) => state.setTournament);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);

  const setDraft = useUserStore((state) => state.setDraft);

  useEffect(() => {}, [tournament.draft, tournament.teams]);

  const handleChange = async (e: FormEvent) => {
    log.debug('createTeamFromCaptainHook', {
      tournament,
    });

    choosePlayerHook({
      tournament,
      setTournament,
      user,
      draft,
      curDraftRound,
      setDraft,
      setCurDraftRound,
    });

    log.debug('updateDraftRound', {
      user: user.username,
      draft_round: curDraftRound.pk,
      draft: draft,
    });
  };

  return (
    <div className="flex flex-row items-center gap-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button>Pick</Button>
        </AlertDialogTrigger>
        <AlertDialogContent className={`bg-green-900`}>
          <AlertDialogHeader>
            <AlertDialogTitle>Choose player {user.username}</AlertDialogTitle>
            <AlertDialogDescription className="text-base-700">
              This Chooses Player {user.username}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleChange}>
              Confirm Pick
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
