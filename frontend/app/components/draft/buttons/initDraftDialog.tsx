import { motion } from 'framer-motion';
import { OctagonAlert } from 'lucide-react';
import { useEffect, type FormEvent } from 'react';
import { initDraftHook } from '~/components/draft/hooks/initDraft';
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
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const setDraftIndex = useUserStore((state) => state.setDraftIndex);
  useEffect(() => {}, [tournament.draft]);
  const isStaff = useUserStore((state) => state.isStaff);
  const handleChange = async (e: FormEvent) => {
    log.debug('handleChange', e);
    if (!tournament) {
      log.error('No tournament found to updatezs');
      return;
    }

    if (tournament.pk === undefined) {
      log.error('No tournament found to update');
      return;
    }

    initDraftHook({ tournament, setTournament });
    setDraftIndex(0);
  };
  if (!isStaff()) {
    return (
      <div className="justify-start flex w-full">
        <AdminOnlyButton tooltipTxt="Must be an admin to make changes to the draft" />
      </div>
    );
  }
  const dialogTriggerButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <AlertDialogTrigger asChild>
              <motion.div
                initial={{ opacity: 0 }}
                exit={{ opacity: 0 }}
                whileInView={{
                  opacity: 1,
                  transition: { delay: 0.05, duration: 0.5 },
                }}
                whileHover={{ scale: 1.1 }}
                whileFocus={{ scale: 1.05 }}
              >
                <Button className="w-40 sm:w-20%" variant={'destructive'}>
                  <OctagonAlert className="mr-2 " />
                  Restart Draft
                </Button>
              </motion.div>
            </AlertDialogTrigger>
          </TooltipTrigger>
          <TooltipContent className="bg-red-900 text-white">
            <p>This will delete draft data and reset the draft choices.</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };
  return (
    <div className="flex w-full justify-start ">
      <AlertDialog>
        {dialogTriggerButton()}
        <AlertDialogContent className={'bg-red-900 text-white'}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Restart Draft? This will delete all choices so far
            </AlertDialogTitle>
            <AlertDialogDescription className="text-base-700">
              This action cannot be undone. Drafts started must be deleted and
              recreated.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleChange}>
              RestartDraft
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
