import { fetchTournament } from '~/components/api/api';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
const log = getLogger('RefreshTournament');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  setDraft?: (draft: DraftType) => void;
  curDraftRound?: DraftRoundType;
  setCurDraftRound?: (draft: DraftRoundType) => void;
};

export const refreshTournamentHook = async ({
  tournament,
  setTournament,
  setDraft,
  curDraftRound,
  setCurDraftRound,
}: hookParams) => {
  log.debug('Refreshing tournament', { tournament });

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

    const rawData = await fetchTournament(tournament.pk);
    const data = hydrateTournament(rawData as TournamentType & { _users?: Record<number, unknown> }) as TournamentType;
    setTournament(data);
    if (setDraft && data.draft) setDraft(data.draft);
    if (setCurDraftRound)
      (log.debug('curDraftRound', { curDraftRound, tournament }),
        setCurDraftRound(
          data.draft?.draft_rounds?.find(
            (round: DraftRoundType) => round?.pk === curDraftRound?.pk,
          ) || ({} as DraftRoundType),
        ));
  } catch (error) {
    log.error('Tournament  has failed to refresh!', error);
  }
};
