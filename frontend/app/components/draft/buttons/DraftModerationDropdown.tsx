import { OctagonAlert, Settings, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
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
import { initDraftRounds } from '~/components/api/api';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('DraftModerationDropdown');

interface DraftModerationDropdownProps {
  onOpenDraftStyleModal: () => void;
}

export const DraftModerationDropdown: React.FC<DraftModerationDropdownProps> = ({
  onOpenDraftStyleModal,
}) => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const loadAll = useTournamentDataStore((state) => state.loadAll);
  const loadDraft = useTeamDraftStore((state) => state.loadDraft);
  const setCurrentRoundIndex = useTeamDraftStore((state) => state.setCurrentRoundIndex);
  const isStaff = useUserStore((state) => state.isStaff);

  const handleRestartDraft = async () => {
    log.debug('handleRestartDraft');
    if (!tournamentId) {
      log.error('No tournament found to update');
      return;
    }

    setIsLoading(true);
    try {
      await toast.promise(
        initDraftRounds({ tournament_pk: tournamentId }),
        {
          loading: 'Initializing draft rounds...',
          success: 'Tournament Draft has been initialized!',
          error: (err) => {
            const val = err.response?.data || 'Unknown error';
            return `Failed to reinitialize tournament draft: ${val}`;
          },
        }
      );

      // Refresh data from server
      await Promise.all([loadAll(), loadDraft()]);
      setCurrentRoundIndex(0);
      setConfirmOpen(false);
    } catch (error) {
      log.error('Failed to restart draft:', error);
    } finally {
      setIsLoading(false);
    }
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
        isLoading={isLoading}
        onConfirm={handleRestartDraft}
      />
    </>
  );
};
