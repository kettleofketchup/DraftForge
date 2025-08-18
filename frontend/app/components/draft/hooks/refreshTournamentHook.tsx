import { fetchTournament } from '~/components/api/api';
import type { TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('RefreshTournament');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
};

export const refreshTournamentHook = async ({
  tournament,
  setTournament,
}: hookParams) => {
  log.debug('Initialization draft', { tournament });

  if (!tournament) {
    log.error('Creating tournamentNo tournament found');
    return;
  }

  if (!tournament.pk) {
    log.error('No tournament primary key found');
    return;
  }

  try {
    log.debug('tournament has been refreshed');
    const data = await fetchTournament(tournament.pk);
    setTournament(data);
  } catch (error) {
    log.error('Tournament  has failed to refresh!', error);
  }
};
