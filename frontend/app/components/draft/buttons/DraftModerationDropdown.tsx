import { OctagonAlert, Settings, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { Button } from '~/components/ui/button';
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
import { useUserStore } from '~/store/userStore';
import { initDraftHook } from '../hooks/initDraftHook';

const log = getLogger('DraftModerationDropdown');

interface DraftModerationDropdownProps {
  onOpenDraftStyleModal: () => void;
}

export const DraftModerationDropdown: React.FC<DraftModerationDropdownProps> = ({
  onOpenDraftStyleModal,
}) => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const isStaff = useUserStore((state) => state.isStaff);

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

    initDraftHook({
      tournament,
      setTournament,
      setDraft,
      curDraftRound,
      setCurDraftRound,
      setDraftIndex,
    });
    setDraftIndex(0);
    setConfirmOpen(false);
  };

  if (!isStaff()) {
    return (
      <AdminOnlyButton tooltipTxt="Must be an admin to manage the draft" />
    );
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="gap-2">
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
          >
            <OctagonAlert className="mr-2 h-4 w-4" />
            Restart Draft
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onOpenDraftStyleModal}>
            <Settings className="mr-2 h-4 w-4" />
            Change Draft Style
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Restart Draft? This will delete all choices so far"
        description="This action cannot be undone. Drafts started must be deleted and recreated."
        confirmLabel="Restart Draft"
        variant="destructive"
        onConfirm={handleRestartDraft}
      />
    </>
  );
};
