import { motion } from 'framer-motion';
import { OctagonAlert } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { initDraftRounds } from '~/components/api/api';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('InitDraftDialog');

export const InitDraftButton: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const loadAll = useTournamentDataStore((state) => state.loadAll);
  const loadDraft = useTeamDraftStore((state) => state.loadDraft);
  const setCurrentRoundIndex = useTeamDraftStore((state) => state.setCurrentRoundIndex);
  const isStaff = useUserStore((state) => state.isStaff);

  const handleChange = async () => {
    log.debug('handleChange');
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
            return `Failed to initialize draft: ${val}`;
          },
        }
      );

      // Refresh data from server
      await Promise.all([loadAll(), loadDraft()]);
      setCurrentRoundIndex(0);
      setOpen(false);
    } catch (error) {
      log.error('Failed to initialize draft:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isStaff()) {
    return (
      <div className="justify-start self-start flex w-full">
        <AdminOnlyButton tooltipTxt="Must be an admin to make changes to the draft" />
      </div>
    );
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <motion.div
              initial={{ opacity: 0 }}
              exit={{ opacity: 0 }}
              whileInView={{
                opacity: 1,
                transition: { delay: 0.05, duration: 0.5 },
              }}
              whileHover={{ scale: 1.1 }}
              whileFocus={{ scale: 1.05 }}
              className="flex place-self-start"
              id="RestartDraftButtonMotion"
            >
              <Button
                className="w-40 sm:w-20%"
                variant="destructive"
                onClick={() => setOpen(true)}
              >
                <OctagonAlert className="mr-2" />
                Restart Draft
              </Button>
            </motion.div>
          </TooltipTrigger>
          <TooltipContent className="bg-red-900 text-white">
            <p>This will delete draft data and reset the draft choices.</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Restart Draft? This will delete all choices so far"
        description="This action cannot be undone. Drafts started must be deleted and recreated."
        confirmLabel="Restart Draft"
        variant="destructive"
        isLoading={isLoading}
        onConfirm={handleChange}
      />
    </>
  );
};
