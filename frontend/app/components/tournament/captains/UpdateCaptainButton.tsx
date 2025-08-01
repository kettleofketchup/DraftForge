import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import type { TournamentType, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('updateCaptainButton');

export const UpdateCaptainButton: React.FC<{ user: UserType }> = ({ user }) => {
  const tournament = useUserStore((state) => state.tournament);

  log.debug(`Adding captain for user: ${user.username}`);

  const updateCaptain = () => {
    var setIsAdding = true;

    if (!tournament) {
      log.error('Creating tournamentNo tournament found');
      return;
    }
    if (!user || !user.pk) {
      log.error('No user found to update captain');
      return;
    }
    if (!tournament.pk) {
      log.error('No tournament primary key found');
      return;
    }
    var newTournament: Partial<TournamentType> = {
      pk: tournament.pk,
      captain_ids: [...tournament.captains.map((c) => c.pk), user.pk],
    };

    if (user.pk in tournament.captains) {
      setIsAdding = false;

      log.debug('User is already a captain, removing instead');
      newTournament.captain_ids = newTournament.captain_ids.filter(
        (id) => id !== user.pk,
      );
    }
    var msg = setIsAdding ? 'Adding' : 'Removing';
    toast.promise(updateTournament(tournament.pk, newTournament), {
      loading: `${msg} ${user.username} as captain...`,
      success: () => {
        return `${tournament?.name} has been updated successfully!`;
      },
      error: (err) => {
        const val = err.response.data;
        log.error('Failed to update captains tournament', err);
        return `Failed to update captains: ${val}`;
      },
    });
  };
  const isAdded = user.pk in tournament.captains;
  const msg = isAdded ? `Remove` : `Add`;

  return <Button onClick={updateCaptain}>{msg} Captain</Button>;
};
