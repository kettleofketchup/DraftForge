import { toast } from 'sonner';
import { initDraftRounds } from '~/components/api/api';
import type { InitDraftRoundsAPI } from '~/components/api/types';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
const log = getLogger('InitDraft');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  setDraft: (draft: DraftType) => void;
  curDraftRound: DraftRoundType;
  setCurDraftRound: (draftRound: DraftRoundType) => void;
  setDraftIndex: (index: number) => void;
};

export const initDraftHook = async ({
  tournament,
  setTournament,
  setDraft,
  curDraftRound,
  setCurDraftRound,
  setDraftIndex,
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
      log.debug('DraftRebuild sucess, data:', data);
      setTournament(data);
      setDraft(data.draft);
      setCurDraftRound(data?.draft?.draft_rounds[0] as DraftRoundType);
      setDraftIndex(0);
      return `Tournament Draft has been initialized!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Tournament Draft has failed to Reinitialize!', err);
      return `Failed to Reinitialize tournament draft: ${val}`;
    },
  });
};
