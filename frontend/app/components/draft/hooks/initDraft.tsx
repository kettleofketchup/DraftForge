import { toast } from 'sonner';
import { DraftRebuild, initDraftRounds } from '~/components/api/api';
import type { InitDraftRoundsAPI } from '~/components/api/types';
import type { TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('InitDraft');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
};

export const initDraftHook = async ({
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

  const data: InitDraftRoundsAPI = {
    tournament_pk: tournament.pk,
  };

  toast.promise(initDraftRounds(data), {
    loading: `Initializing draft rounds...`,
    success: (data) => {
      setTournament(data);
      return `Tournament Draft has been initialized!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Tournament Draft has failed to Reinitialize!', err);
      return `Failed to Reinitialize tournament draft: ${val}`;
    },
  });

  toast.promise(DraftRebuild(data), {
    loading: `Rebuilding teams...`,
    success: (data) => {
      setTournament(data);
      return `Tournament Draft has been rebuilt!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Tournament Draft has failed to Rebuild!', err);
      return `Failed to Rebuild tournament draft: ${val}`;
    },
  });
};
