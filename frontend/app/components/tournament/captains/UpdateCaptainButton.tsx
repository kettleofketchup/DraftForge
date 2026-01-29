import { useEffect, useMemo, useState, type FormEvent } from 'react';
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
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import { useUserStore } from '~/store/userStore';
import { createTeamFromCaptainHook } from './createTeamFromCaptainHook';
import { DraftOrderButton } from './draftOrder';
const log = getLogger('updateCaptainButton');
export const UpdateCaptainButton: React.FC<{ user: UserType }> = ({ user }) => {
  const tournament = useTournamentDataStore((state) => state.tournament);
  const teams = useTournamentDataStore((state) => state.teams);
  const loadFull = useTournamentDataStore((state) => state.loadFull);
  const isStaff = useUserStore((state) => state.isStaff);

  // Derive captains from teams (each team has a captain)
  const captains = useMemo(() => {
    return teams.map((t) => t.captain).filter((c): c is UserType => c !== null && c !== undefined);
  }, [teams]);

  const isCaptainDerived = useMemo(() => {
    return captains.some((c) => c.pk === user.pk);
  }, [captains, user.pk]);

  const team = useMemo(() => {
    return teams.find((t: TeamType) => t.captain?.pk === user.pk);
  }, [teams, user.pk]);

  const [isCaptain, setIsCaptain] = useState<boolean>(isCaptainDerived);

  const getDraftOrder = () => {
    if (!isCaptain) return '0';
    if (!team) return '0';
    if (team.draft_order) return String(team.draft_order);
    return '0';
  };

  const [draft_order, setDraftOrder] = useState<string>(getDraftOrder());
  const msg = () => (isCaptain ? `Remove` : `Add`);

  const getButtonVariant = (): 'destructive' | 'default' => isCaptain ? 'destructive' : 'default';

  useEffect(() => {
    setIsCaptain(isCaptainDerived);
  }, [isCaptainDerived]);

  const handleChange = async (e: FormEvent) => {
    log.debug('handleChange', e);
    if (!tournament) return;
    await createTeamFromCaptainHook({
      tournament,
      captain: user,
      draft_order: draft_order,
      setDraftOrder: setDraftOrder,
      reloadTournament: loadFull,
      setIsCaptain: setIsCaptain,
    });
  };
  const dialogBG = () => (isCaptain ? 'bg-red-900' : 'bg-green-900');
  if (!isStaff()) return <AdminOnlyButton buttonTxt="Change Captain" />;

  return (
    <div
      className="flex flex-col gap-y-2 justify-between
    justify-between items-center align-middle w-full md:flex-row md:gap-x-2 md:py-1"
    >
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
            <AlertDialogDescription className="text-slate-200">
              This action cannot be undone. Drafts started must be deleted and
              recreated.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <CancelButton variant={isCaptain ? 'default' : 'destructive'} depth={false}>Cancel</CancelButton>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <ConfirmButton
                onClick={handleChange}
                variant={isCaptain ? 'destructive' : 'default'}
                depth={false}
              >
                {msg()} Captain
              </ConfirmButton>
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
