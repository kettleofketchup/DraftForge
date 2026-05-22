import { useEffect, useState } from 'react';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { DestructiveButton, PrimaryButton } from '~/components/ui/buttons';
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { createTeamFromCaptainHook } from './createTeamFromCaptainHook';
import { DraftOrderButton } from './draftOrder';
const log = getLogger('updateCaptainButton');
export const UpdateCaptainButton: React.FC<{ user: UserType }> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);
  const isStaff = useUserStore((state) => state.isStaff);

  const determineIsCaptain = () => {
    return !!tournament?.captains?.some((c) => c.pk === user.pk);
  };
  const getTeam = () => {
    return tournament?.teams?.find((t: TeamType) => t.captain?.pk === user.pk);
  };
  const [isCaptain, setIsCaptain] = useState<boolean>(determineIsCaptain());
  const [showConfirm, setShowConfirm] = useState(false);
  const setTournament = useUserStore((state) => state.setTournament);

  const getDraftOrder = () => {
    if (!isCaptain) return '0';
    const team = getTeam();
    if (!team) return '0';
    if (team.draft_order) return String(team.draft_order);
    return '0';
  };

  const [draft_order, setDraftOrder] = useState<string>(getDraftOrder());
  const msg = () => (isCaptain ? `Remove` : `Add`);

  useEffect(() => {
    setIsCaptain(determineIsCaptain());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tournament?.captains, user.pk]);

  const handleChange = async () => {
    log.debug('handleChange');
    await createTeamFromCaptainHook({
      tournament,
      captain: user,
      draft_order: draft_order,
      setDraftOrder: setDraftOrder,
      setTournament: setTournament,
      setIsCaptain: setIsCaptain,
    });
  };
  if (!isStaff()) return <AdminOnlyButton buttonTxt="Change Captain" />;

  return (
    <div
      className="flex flex-col gap-y-2 justify-between
    justify-between items-center align-middle w-full md:flex-row md:gap-x-2 md:py-1"
    >
      {isCaptain ? (
        <DestructiveButton className="w-40" onClick={() => setShowConfirm(true)}>{msg()} Captain</DestructiveButton>
      ) : (
        <PrimaryButton className="w-40" onClick={() => setShowConfirm(true)}>{msg()} Captain</PrimaryButton>
      )}
      <ConfirmDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title={`${msg()} Captain? Are You Sure? This will affect already created teams and drafts`}
        description="This action cannot be undone. Drafts started must be deleted and recreated."
        confirmLabel={`${msg()} Captain`}
        variant={isCaptain ? 'destructive' : 'default'}
        onConfirm={handleChange}
      />
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
