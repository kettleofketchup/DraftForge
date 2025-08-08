import { toast } from 'sonner';
import { updateDraftRound } from '~/components/api/api';
import type { UserType } from '~/components/user/types';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
import { rebuildTeamsHook } from './rebuildTeamHook';
const log = getLogger('ChoosePlayerHook');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  user: UserType;
  draft: DraftType;
  curDraftRound: DraftRoundType;
  setDraft: (draft: DraftType) => void;
  setCurDraftRound: (draftRound: DraftRoundType) => void;
};

export const choosePlayerHook = async ({
  tournament,
  setTournament,
  user,
  draft,
  curDraftRound,
  setDraft,
  setCurDraftRound,
}: hookParams) => {
  log.debug('createTeamFromCaptainHook', { tournament, user });
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

 
  log.debug(
    `Choosing player ${user.username} for captain  ${curDraftRound.captain?.username}`,
  );

  const dataRoundUpdate: Partial<DraftRoundType> = {
    choice_id: user.pk,
    pk: curDraftRound.pk,
  };

  toast.promise(updateDraftRound(curDraftRound.pk, dataRoundUpdate), {
    loading: `Choosing ${user.username} for ${curDraftRound.captain?.username}  in round ${curDraftRound.pick_number}`,
    success: (data) => {
      setCurDraftRound(data);

      return `${curDraftRound?.pick_number} has been updated successfully!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Failed to update captains tournament', err);
      return `Failed to update captains: ${val}`;
    },
  });
  rebuildTeamsHook({
    tournament: tournament,
    setTournament: setTournament,
  });
};
