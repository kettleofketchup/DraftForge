import { motion } from 'framer-motion';
import { OctagonAlert } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { initDraftHook } from '~/components/draft/hooks/initDraftHook';
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

const log = getLogger('InitDraftDialog');

export const InitDraftButton: React.FC = () => {
  const [open, setOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const isStaff = useUserStore((state) => state.isStaff);

  const handleChange = async () => {
    log.debug('handleChange');
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
    setOpen(false);
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
        onConfirm={handleChange}
      />
    </>
  );
};
