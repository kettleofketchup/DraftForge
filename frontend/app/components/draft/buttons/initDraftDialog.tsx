import { useEffect, type FormEvent } from 'react';
import { initDraftHook } from '~/components/draft/hooks/initDraft';
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
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('InitDraftDialog');
export const InitDraftButton: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);

  useEffect(() => {}, [tournament.draft]);

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
  };
  return (
    <div className="flex flex-row items-center gap-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant={'destructive'}>Restart Draft</Button>
        </AlertDialogTrigger>
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
