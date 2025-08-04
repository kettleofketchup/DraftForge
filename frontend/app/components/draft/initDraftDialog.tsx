import { useEffect, type FormEvent } from 'react';
import { toast } from 'sonner';
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
import { initDraftRounds } from '../api/api';
import type { InitDraftRoundsAPI } from '../api/types';
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
    const data: InitDraftRoundsAPI = {
      tournament_pk: tournament.pk,
    };
    toast.promise(initDraftRounds(data), {
      loading: `Initializing draft rounds for ${tournament?.name}`,
      success: (data) => {
        setTournament(data);
        return `Draft rounds initialized for ${data?.name}`;
      },
      error: (err) => {
        log.error('Failed to initialize draft rounds', err);
        return `Failed to initialize draft rounds: ${err.message}`;
      },
    });
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
