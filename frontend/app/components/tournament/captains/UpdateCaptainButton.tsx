import { Crown, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { DestructiveButton, PrimaryButton } from '~/components/ui/buttons';
import type { TeamType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { createTeamFromCaptainHook } from './createTeamFromCaptainHook';
import { DraftOrderButton } from './draftOrder';
const log = getLogger('updateCaptainButton');

interface UpdateCaptainButtonProps {
  user: UserType;
  /**
   * `compact=true` renders an icon-only action sized for a UserStrip's
   * actionSlot (36×36 touch target with a Crown / X glyph). Default mode
   * keeps the original wide `w-40` "Add Captain" / "Remove Captain" pill
   * used by the legacy table layout.
   */
  compact?: boolean;
  /**
   * Hide the draft-order picker. Useful when the strip puts draft order in
   * a separate contextSlot.
   */
  hideDraftOrder?: boolean;
}

export const UpdateCaptainButton: React.FC<UpdateCaptainButtonProps> = ({
  user,
  compact = false,
  hideDraftOrder = false,
}) => {
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

  if (!isStaff()) {
    return compact ? (
      <div className="flex flex-col items-stretch gap-0.5 w-9">
        <span
          className="text-[9px] uppercase tracking-wider text-muted-foreground leading-none text-center"
          aria-hidden
        >
          {isCaptain ? 'Remove' : 'Pick'}
        </span>
        <AdminOnlyButton
          buttonTxt=""
          className="h-9 w-9 p-0 [&_svg]:size-4 [&_svg]:mr-0"
          iconClassName=""
          data-testid={`captain-action-locked-${user.pk}`}
        />
      </div>
    ) : (
      <AdminOnlyButton buttonTxt="Change Captain" />
    );
  }

  const triggerClass = cn(
    compact ? 'h-9 w-9 p-0 [&_svg]:size-4' : 'w-40',
  );

  const compactLabel = isCaptain ? 'Remove' : 'Pick';

  return (
    <div
      className={cn(
        compact
          ? 'flex flex-col items-stretch gap-0.5 w-9'
          : 'flex flex-col gap-y-2 justify-between items-center align-middle w-full md:flex-row md:gap-x-2 md:py-1',
      )}
    >
      {compact && (
        <span
          className="text-[9px] uppercase tracking-wider text-muted-foreground leading-none text-center"
          aria-hidden
        >
          {compactLabel}
        </span>
      )}
      {isCaptain ? (
        <DestructiveButton
          className={triggerClass}
          onClick={() => setShowConfirm(true)}
          aria-label={compact ? `${msg()} captain ${user.username ?? ''}`.trim() : undefined}
          data-testid={`captain-action-${user.pk}`}
        >
          {compact ? <X /> : `${msg()} Captain`}
        </DestructiveButton>
      ) : (
        <PrimaryButton
          className={triggerClass}
          onClick={() => setShowConfirm(true)}
          aria-label={compact ? `${msg()} captain ${user.username ?? ''}`.trim() : undefined}
          data-testid={`captain-action-${user.pk}`}
        >
          {compact ? <Crown /> : `${msg()} Captain`}
        </PrimaryButton>
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
      {isCaptain && !hideDraftOrder && (
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
