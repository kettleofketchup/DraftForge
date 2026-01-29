import { toast } from 'sonner';
import { DraftRebuild } from '~/components/api/api';
import type { RebuildDraftRoundsAPI } from '~/components/api/types';
import type { TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('Rebuild Teams Hook');

type hookParams = {
  tournament: TournamentType;
  reloadTournament: () => Promise<void>;
};

export const rebuildTeamsHook = async ({
  tournament,
  reloadTournament,
}: hookParams) => {
  log.debug('Rebuilding teams', { tournament });

  if (!tournament) {
    log.error('No tournament found');
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
    success: async () => {
      await reloadTournament();
      return `Tournament Draft has been rebuilt!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Tournament Draft has failed to Rebuild!', err);
      return `Failed to Rebuild tournament draft: ${val}`;
    },
  });
};
