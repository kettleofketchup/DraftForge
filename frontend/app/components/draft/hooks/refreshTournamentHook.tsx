import { getLogger } from '~/lib/logger';
const log = getLogger('RefreshTournament');

type hookParams = {
  tournamentId: number;
  reloadTournament: () => Promise<void>;
};

/**
 * Refresh tournament data by reloading from the store.
 * Uses the single source of truth pattern - store handles the fetch internally.
 */
export const refreshTournamentHook = async ({
  tournamentId,
  reloadTournament,
}: hookParams) => {
  log.debug('Refreshing tournament', { tournamentId });

  if (!tournamentId) {
    log.error('No tournament ID provided');
    return;
  }

  try {
    await reloadTournament();
    log.debug('Tournament has been refreshed');
  } catch (error) {
    log.error('Tournament has failed to refresh!', error);
  }
};
