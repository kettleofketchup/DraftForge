import { useEffect, useState, type FormEvent } from 'react';
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
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { createTeamFromCaptainHook } from './createTeamFromCaptainHook';
const log = getLogger('updateCaptainButton');

import { DraftOrderButton } from './draftOrder';
export const UpdateCaptainButton: React.FC<{ user: UserType }> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);
  const determineIsCaptain = () => {
    return !!tournament?.captains?.some((c) => c.pk === user.pk);
  };
  const getTeam = () => {
    return tournament?.teams?.find((t: TeamType) => t.captain.pk === user.pk);
  };
  const [isCaptain, setIsCaptain] = useState<boolean>(determineIsCaptain());
  const setTournament = useUserStore((state) => state.setTournament);
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  );
  const getDraftOrder = () => {
    if (!isCaptain) return '0';
    const team = getTeam();
    if (!team) return '0';
    if (team.draft_order) return String(team.draft_order);
    return '0';
  };

  const [draft_order, setDraftOrder] = useState<string>(getDraftOrder());

  const msg = () => (isCaptain ? `Remove` : `Add`);

  const getButtonVariant = () => `${isCaptain ? 'destructive' : 'default'}`;

  useEffect(() => {
    setIsCaptain(determineIsCaptain());
  }, [tournament.captains, tournament.teams, isCaptain, draft_order]);

  const handleChange = async (e: FormEvent) => {
    log.debug('handleChange', e);
    await createTeamFromCaptainHook({
      tournament,
      captain: user,
      draft_order: draft_order,
      setTournament: setTournament,
      setIsCaptain: setIsCaptain,
    });
  };
  const dialogBG = () => (isCaptain ? 'bg-red-900' : 'bg-green-900');
  return (
    <div className="flex flex-row items-center gap-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant={getButtonVariant()}>{msg()} Captain</Button>
        </AlertDialogTrigger>
        <AlertDialogContent className={dialogBG()}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {' '}
              {msg()} Captain? Are You Sure? This will affect already created
              teams and drafts
            </AlertDialogTitle>
            <AlertDialogDescription className="text-base-700">
              This action cannot be undone. Drafts started must be deleted and
              recreated.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleChange}>
              {msg()} Captain
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {isCaptain && (
        <DraftOrderButton
          id={`draft-order-${user.pk}`}
          user={user}
          draft_order={draft_order}
          setDraftOrder={setDraftOrder}
        />
      )}
    </div>
  );
};
