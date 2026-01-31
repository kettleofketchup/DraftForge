import { toast } from 'sonner';
import { DraftRebuild } from '~/components/api/api';
import type { RebuildDraftRoundsAPI } from '~/components/api/types';
import type { TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('Rebuild Teams Hook');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
};

export const rebuildTeamsHook = async ({
  tournament,
  setTournament,
}: hookParams) => {
  log.debug('Rebuilding teams', { tournament });

  if (!tournament) {
    log.error('Creating tournamentNo tournament found');
    return;
  }

  if (!tournament.pk) {
    log.error('No tournament primary key found');
    return;
  }

  const data: RebuildDraftRoundsAPI = {
    tournament_pk: tournament.pk,
  };

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
