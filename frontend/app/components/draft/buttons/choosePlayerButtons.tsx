import { useState, useEffect, type FormEvent } from 'react';
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
import type { UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { choosePlayerHook } from '../hooks/choosePlayerHook';
import { refreshDraftHook } from '../hooks/refreshDraftHook';
import { TieResolutionOverlay } from '../TieResolutionOverlay';
import type { TieResolution } from '../types';
const log = getLogger('pickPlayerButton');

export const ChoosePlayerButton: React.FC<{
  user: UserType;
}> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);

  const setTournament = useUserStore((state) => state.setTournament);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);
  const isStaff = useUserStore((state) => state.isStaff);

  const setDraft = useUserStore((state) => state.setDraft);

  const [tieResolution, setTieResolution] = useState<TieResolution | null>(
    null,
  );
  const [showTieOverlay, setShowTieOverlay] = useState(false);

  useEffect(() => {}, [tournament.draft, tournament.teams]);

  const handleChange = async (e: FormEvent) => {
    log.debug('ChoosePlayerButton: Tournament', {
      tournament,
    });

    choosePlayerHook({
      tournament,
      setTournament,
      player: user,
      curDraftRound,
      setCurDraftRound,
      setDraft,
      onTieResolution: (resolution) => {
        setTieResolution(resolution);
        setShowTieOverlay(true);
      },
    });
    refreshDraftHook({ draft, setDraft });

    log.debug('updateDraftRound', {
      user: user.username,
      draft_round: curDraftRound.pk,
      draft: draft,
    });
  };
  if (!isStaff()) {
    return (
      <>
        <AdminOnlyButton buttonTxt="Only Staff Can Pick" />
      </>
    );
  }
  return (
    <>
      <div className="flex flex-row items-center gap-4">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button>Pick</Button>
          </AlertDialogTrigger>
          <AlertDialogContent className={`bg-green-900`}>
            <AlertDialogHeader>
              <AlertDialogTitle>
                Choose player {user.username}
              </AlertDialogTitle>
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
