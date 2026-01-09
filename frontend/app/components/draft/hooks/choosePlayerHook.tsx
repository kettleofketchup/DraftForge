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
  setDraftIndex: (index: number) => void;
  onTieResolution?: (tieResolution: TieResolution) => void;
  autoRefreshDraft?: () => Promise<void>;
};

export const choosePlayerHook = async ({
  tournament,
  setTournament,
  player,
  curDraftRound,
  setDraft,
  setCurDraftRound,
  setDraftIndex,
  onTieResolution,
  autoRefreshDraft,
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
    `Choosing player ${player.nickname || player.username} for captain ${curDraftRound.captain?.nickname || curDraftRound.captain?.username}`,
  );

  const dataRoundUpdate: PickPlayerForRoundAPI = {
    draft_round_pk: curDraftRound.pk,
    user_pk: player.pk,
  };

  const getDraft = (tournament: TournamentType) => {
    return tournament.draft as DraftType;
  };
  const getDraftRound = (draft: DraftType, roundPk: number) => {
    return draft.draft_rounds?.find(
      (round: DraftRoundType) => round.pk === roundPk,
    );
  };
  toast.promise(PickPlayerForRound(dataRoundUpdate), {
    loading: `Choosing ${player.nickname || player.username} for ${curDraftRound.captain?.nickname || curDraftRound.captain?.username} in round ${curDraftRound.pick_number}`,
    success: (data) => {
      setTournament(data);
      setDraft(data.draft);

      // Find and advance to next round (first with captain assigned but no choice)
      const nextRound = data.draft.draft_rounds?.find(
        (r: DraftRoundType) => r.captain && !r.choice,
      );

      if (nextRound) {
        setCurDraftRound(nextRound);
        const idx = data.draft.draft_rounds?.findIndex(
          (r: DraftRoundType) => r.pk === nextRound.pk,
        );
        if (idx !== undefined && idx >= 0) {
          setDraftIndex(idx);
        }
        log.debug('Advanced to next round', nextRound);
      } else {
        // No more rounds with captains, stay on current (now completed) round
        const updatedRound = data.draft.draft_rounds?.find(
          (round: DraftRoundType) => round.pk === curDraftRound.pk,
        );
        if (updatedRound) {
          setCurDraftRound(updatedRound);
        }
        log.debug('No more rounds to advance to');
      }

      // Show tie overlay for shuffle draft
      // Cast data to include tie_resolution from backend
      const responseData = data as TournamentType & {
        tie_resolution?: TieResolution;
      };
      if (
        responseData.draft?.draft_style === 'shuffle' &&
        responseData.tie_resolution &&
        onTieResolution
      ) {
        onTieResolution(responseData.tie_resolution);
      }

      // Trigger auto-refresh after successful pick
      if (autoRefreshDraft) {
        autoRefreshDraft();
      }

      return `Pick ${curDraftRound?.pick_number} complete!`;
    },
    error: (err) => {
      const val = err.response.data;
      log.error('Failed to update captains tournament', err);
      return `Failed to update captains: ${val}`;
    },
  });
};
