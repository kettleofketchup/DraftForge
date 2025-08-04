import type { JSX } from 'react';
import { toast } from 'sonner';
import {
  createTeamFromCaptain,
  deleteTeam,
  fetchTournament,
} from '~/components/api/api';
import type { CreateTeamFromCaptainAPI } from '~/components/api/types';
import type { UserType } from '~/components/user/types';
import { getLogger } from '~/lib/logger';
import type { TournamentType } from '../types';
const log = getLogger('handleSaveHook');

export const createErrorMessage = (
  val: Partial<Record<keyof UserType, string>>,
): JSX.Element => {
  if (!val || Object.keys(val).length === 0)
    return <h5>Error creating user:</h5>;

  return (
    <div className="text-error">
      <ul>
        {Object.entries(val).map(([field, message]) => (
          <li key={field}>{message}</li>
        ))}
      </ul>
    </div>
  );
};

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  captain: UserType;
  draft_order: string;
  setDraftOrder?: React.Dispatch<React.SetStateAction<string>>;

  setIsCaptain?: (value: React.SetStateAction<boolean>) => void;
};

export const createTeamFromCaptainHook = async ({
  tournament,
  setTournament,
  captain,
  draft_order,
  setDraftOrder,
  setIsCaptain,
}: hookParams) => {
  const isCaptain = () => {
    return !!tournament?.captains?.some((c) => c.pk === captain.pk);
  };

  log.debug('createTeamFromCaptainHook', { tournament, captain, draft_order });
  if (!tournament) {
    log.error('Creating tournamentNo tournament found');
    return;
  }
  if (!captain || !captain.pk) {
    log.error('No user found to update captain');
    return;
  }
  if (!tournament.pk) {
    log.error('No tournament primary key found');
    return;
  }

  const getTeam = () => {
    return tournament?.teams?.find((t) => t.captain.pk === captain.pk);
  };
  var newTournament: Partial<TournamentType> = {
    pk: tournament.pk,
  };
  const team = getTeam();
  if (team && team.pk) {
    log.debug(`Team found for captain: ${captain.username}...deleting team`);
    if (team.captain && team.captain.pk === captain.pk) setIsCaptain?.(false);
    toast.promise(deleteTeam(getTeam().pk), {
      loading: `Deleting team for ${captain.username}`,
      success: () => {
        setDraftOrder?.('0');
        return `Team for ${captain.username} has been deleted`;
      },
      error: (err) => {
        log.error('Failed to delete team', err);
        return `Failed to delete team: ${err.message}`;
      },
    });
    const data = await fetchTournament(tournament.pk);
    setTournament(data);
    // If the captain is being removed, update state
    return;
  }

  log.debug('Creating team for captain', captain.username);

  const data: CreateTeamFromCaptainAPI = {
    user_pk: captain.pk,
    tournament_pk: tournament.pk,
    draft_order: parseInt(draft_order),
  };

  var msg = isCaptain() ? 'Removing' : 'adding';
  log.debug(`${msg} captain for user: ${captain.username}`, newTournament);

  toast.promise(createTeamFromCaptain(data), {
    loading: `${msg} ${captain.username} as captain...`,
    success: (data) => {
      setTournament(data);

      if (setIsCaptain) setIsCaptain(!isCaptain());

      return `${tournament?.name} has been updated successfully!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Failed to update captains tournament', err);
      return `Failed to update captains: ${val}`;
    },
  });
};
