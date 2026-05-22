import { Crown, X } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
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
import { CancelButton, ConfirmButton, DestructiveButton, PrimaryButton } from '~/components/ui/buttons';
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
   * actionSlot (32x32 touch target with a Crown / X glyph). Default mode
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
  }, [tournament.captains, tournament.teams, isCaptain, draft_order]);

  const handleChange = async (e: FormEvent) => {
    log.debug('handleChange', e);
    await createTeamFromCaptainHook({
      tournament,
      captain: user,
      draft_order: draft_order,
      setDraftOrder: setDraftOrder,
      setTournament: setTournament,
      setIsCaptain: setIsCaptain,
    });
  };
  const dialogBG = () => (isCaptain ? 'bg-red-900' : 'bg-green-900');
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

  // Compact mode: stack a small "Pick" / "Remove" label above the icon
  // button to match the "Order" subtitle on the DraftOrder picker below.
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
      <AlertDialog>
        <AlertDialogTrigger asChild>
          {isCaptain ? (
            <DestructiveButton
              className={triggerClass}
              aria-label={compact ? `${msg()} captain ${user.username ?? ''}`.trim() : undefined}
              data-testid={`captain-action-${user.pk}`}
            >
              {compact ? <X /> : `${msg()} Captain`}
            </DestructiveButton>
          ) : (
            <PrimaryButton
              className={triggerClass}
              aria-label={compact ? `${msg()} captain ${user.username ?? ''}`.trim() : undefined}
              data-testid={`captain-action-${user.pk}`}
            >
              {compact ? <Crown /> : `${msg()} Captain`}
            </PrimaryButton>
          )}
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
