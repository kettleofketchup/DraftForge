import { toast } from 'sonner';
import { PickPlayerForRound } from '~/components/api/api';
import type { PickPlayerForRoundAPI } from '~/components/api/types';
import type { UserType } from '~/components/user/types';
import type { DraftRoundType, DraftType, TournamentType } from '~/index';
import { getLogger } from '~/lib/logger';
import type { TieResolution } from '../types';
const log = getLogger('PickPlayerHook');

type hookParams = {
  tournament: TournamentType;
  setTournament: (tournament: TournamentType) => void;
  player: UserType;
  curDraftRound: DraftRoundType;
  setDraft: (draft: DraftType) => void;
  setCurDraftRound: (draftRound: DraftRoundType) => void;
  onTieResolution?: (tieResolution: TieResolution) => void;
};

export const choosePlayerHook = async ({
  tournament,
  setTournament,
  player,
  curDraftRound,
  setDraft,
  setCurDraftRound,
  onTieResolution,
}: hookParams) => {
  if (!tournament || !tournament.pk) {
    log.error('No tournament found');
    return;
  }
  if (!player || !player.pk) {
    log.error('No user found to choose');
    return;
  }
  if (!curDraftRound || !curDraftRound.pk) {
    log.error('No current draft round found');
    return;
  }

  log.debug(
    `Choosing player ${player.username} for captain  ${curDraftRound.captain?.username}`,
  );

  const dataRoundUpdate: PickPlayerForRoundAPI = {
    draft_round_pk: curDraftRound.pk,
    user_pk: player.pk,
  };

  const getDraft = (tournament: TournamentType) => {
    return tournament.draft as DraftType;
  };
  const getDraftRound = (draft: DraftType, roundPk: number) => {
    return draft.draft_rounds?.find((round) => round.pk === roundPk);
  };
  toast.promise(PickPlayerForRound(dataRoundUpdate), {
    loading: `Choosing ${player.username} for ${curDraftRound.captain?.username} in round ${curDraftRound.pick_number}`,
    success: (data) => {
      let newRound: DraftRoundType = data.draft.draft_rounds?.find(
        (round: DraftRoundType) => round.pk === curDraftRound.pk,
      );

      log.debug('newRound', newRound);
      log.debug('draft', data.draft);
      setTournament(data);
      setDraft(data.draft);
      setCurDraftRound(newRound);

      // Show tie overlay for shuffle draft
      if (
        data.draft?.draft_style === 'shuffle' &&
        data.tie_resolution &&
        onTieResolution
      ) {
        onTieResolution(data.tie_resolution);
      }

      return `${curDraftRound?.pick_number} has been updated successfully!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Failed to update captains tournament', err);
      return `Failed to update captains: ${val}`;
    },
  });
};
