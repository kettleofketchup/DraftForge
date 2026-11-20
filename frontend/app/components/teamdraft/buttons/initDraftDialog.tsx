import { motion } from 'framer-motion';
import { OctagonAlert } from 'lucide-react';
import { useState } from 'react';
import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { initDraftHook } from '~/components/teamdraft/hooks/initDraftHook';
import { useConfirmForceReset } from '~/components/teamdraft/hooks/useConfirmForceReset';
import { useDraftResetSummary } from '~/components/teamdraft/hooks/useDraftResetSummary';
import { Button } from '~/components/ui/button';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('InitDraftDialog');

// Stable animation objects to prevent re-renders
const inViewAnimation = {
  opacity: 1,
  transition: { delay: 0.05, duration: 0.5 },
};
const hoverAnimation = { scale: 1.1 };
const focusAnimation = { scale: 1.05 };

export const InitDraftButton: React.FC = () => {
  const [open, setOpen] = useState(false);
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);
  const setDraft = useUserStore((state) => state.setDraft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);
  const isStaff = useUserStore((state) => state.isStaff);
  const { confirmForce, confirmForceDialog } = useConfirmForceReset();
  const { showResetSummary, resetSummaryDialog } = useDraftResetSummary();

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

    void initDraftHook({
      tournament,
      setTournament,
      setDraft,
      curDraftRound,
      setCurDraftRound,
      confirmForce,
      onReport: showResetSummary,
    });
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
      <Tooltip>
        <TooltipTrigger asChild>
          <motion.div
            initial={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            whileInView={inViewAnimation}
            whileHover={hoverAnimation}
            whileFocus={focusAnimation}
            className="flex place-self-start"
            id="RestartDraftButtonMotion"
          >
            <Button
              className="w-40"
              variant="destructive"
              onClick={() => setOpen(true)}
            >
              <OctagonAlert className="mr-2" />
              Restart Draft
            </Button>
          </motion.div>
        </TooltipTrigger>
        <TooltipContent className="bg-destructive text-white">
          <p>This clears the picks and resets every team to its captain.</p>
        </TooltipContent>
      </Tooltip>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Restart Draft? Teams will be reset to their captains"
        description="Every pick so far is cleared and each team goes back to just its captain. Games and other records that use the teams are kept."
        confirmLabel="Restart Draft"
        variant="destructive"
        onConfirm={handleChange}
      />
      {confirmForceDialog}
      {resetSummaryDialog}
    </>
  );
};
