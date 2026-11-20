import { OctagonAlert, Settings, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Button } from '~/components/ui/button';
import { brandErrorBg } from '~/components/ui/buttons/styles';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { initDraftHook } from '../hooks/initDraftHook';
import { useConfirmForceReset } from '../hooks/useConfirmForceReset';
import { useDraftResetSummary } from '../hooks/useDraftResetSummary';

const log = getLogger('DraftModerationDropdown');

interface DraftModerationDropdownProps {
  onOpenDraftStyleModal: () => void;
}

export const DraftModerationDropdown: React.FC<
  DraftModerationDropdownProps
> = ({ onOpenDraftStyleModal }) => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const isStaff = useUserStore((state) => state.isStaff);
  const { confirmForce, confirmForceDialog } = useConfirmForceReset();
  const { showResetSummary, resetSummaryDialog } = useDraftResetSummary();

  const handleRestartDraft = async () => {
    log.debug('handleRestartDraft');
    if (!tournament) {
      log.error('No tournament found to update');
      return;
    }

    if (tournament.pk === undefined) {
      log.error('No tournament found to update');
      return;
    }

    setConfirmOpen(false);
    void initDraftHook({
      tournament,
      setTournament,
      setDraft,
      curDraftRound,
      setCurDraftRound,
      confirmForce,
      onReport: showResetSummary,
    });
  };

  // Hide moderation controls entirely for non-staff users
  if (!isStaff()) {
    return null;
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className={cn('gap-2 text-white', brandErrorBg)}
          >
            <ShieldAlert className="h-4 w-4" />
            <span className="hidden sm:inline">Moderation</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Draft Moderation</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setConfirmOpen(true)}
            className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-950/20"
            data-testid="restart-draft-option"
          >
            <OctagonAlert className="mr-2 h-4 w-4" />
            Restart Draft
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={onOpenDraftStyleModal}
            data-testid="change-draft-style-option"
          >
            <Settings className="mr-2 h-4 w-4" />
            Change Draft Style
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Restart Draft? Teams will be reset to their captains"
        description="Every pick so far is cleared and each team goes back to just its captain. Games and other records that use the teams are kept."
        confirmLabel="Restart Draft"
        variant="destructive"
        onConfirm={handleRestartDraft}
        confirmTestId="restart-draft-confirm"
      />
      {confirmForceDialog}
      {resetSummaryDialog}
    </>
  );
};
