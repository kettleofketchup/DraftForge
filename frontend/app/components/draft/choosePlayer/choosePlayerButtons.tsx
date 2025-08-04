import { useEffect, type FormEvent } from 'react';
import { toast } from 'sonner';
import { DraftRebuild, updateDraftRound } from '~/components/api/api';
import type { RebuildDraftRoundsAPI } from '~/components/api/types';
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
import type { DraftRoundType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('pickPlayerButton');
export const ChoosePlayerButton: React.FC<{
  user: UserType;
  curRound: DraftRoundType;
}> = ({ user, curRound }) => {
  const tournament = useUserStore((state) => state.tournament);

  const setTournament = useUserStore((state) => state.setTournament);
  const draft = useUserStore((state) => state.draft);

  const setDraft = useUserStore((state) => state.setDraft);

  useEffect(() => {}, [tournament.draft, tournament.teams]);

  const handleChange = async (e: FormEvent) => {
    log.debug('createTeamFromCaptainHook', {
      tournament,
    });
    if (!tournament) {
      log.error('Creating tournamentNo tournament found');
      return;
    }

    if (!tournament.pk) {
      log.error('No tournament primary key found');
      return;
    }

    const getTeam = () => {
      return tournament?.teams?.find(
        (t) => t.captain.pk === curRound?.captain?.pk,
      );
    };

    const team = getTeam();

    var newDraftRound: DraftRoundType = {
      pk: curRound.pk,
      choice_id: user.pk,
    };
    log.debug('updateDraftRound', {
      user: user.username,
      draft_round: curRound.pk,
      team: team?.name,
    });
    toast.promise(updateDraftRound(curRound.pk, newDraftRound), {
      loading: `choosing player ${user.username}  for ${tournament.name}`,
      success: (data) => {
        return `${tournament?.name} has been updated successfully!`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update draft round with choice', err);
        return `Failed to update captains: ${val}`;
      },
    });

    const rebuildData: RebuildDraftRoundsAPI = {
      tournament_pk: tournament.pk,
    };

    toast.promise(DraftRebuild(rebuildData), {
      loading: `Rebuilding teams with draft for ${tournament.name}`,
      success: (data) => {
        setTournament(data);
        setDraft(data.draft);

        return `${tournament?.name} has been updated successfully!`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update draft round with choice', err);
        return `Failed to update captains: ${val}`;
      },
    });
  };

  return (
    <div className="flex flex-row items-center gap-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button>Pick</Button>
        </AlertDialogTrigger>
        <AlertDialogContent className={`bg-green-900`}>
          <AlertDialogHeader>
            <AlertDialogTitle>Choose player {user.username}</AlertDialogTitle>
            <AlertDialogDescription className="text-base-700">
              This Chooses Player {user.username}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleChange}>
              Confirm Pick
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
