import React, { useEffect, useMemo } from 'react';
import { DisplayName } from '~/components/user/avatar';
import { useUserStore } from '~/store/userStore';
import { useTeamDraftStore } from '~/store/teamDraftStore';

/**
 * Indicator showing whose turn it is in the draft.
 *
 * Displays a prominent message when it's the current user's turn,
 * or shows which captain is currently picking.
 */
export const TurnIndicator: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  // Only subscribe to draft_rounds (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);

  const isMyTurn = currentUser?.pk === curDraftRound?.captain?.pk;
  const captainName = curDraftRound?.captain ? DisplayName(curDraftRound.captain) : 'Unknown';
  const pickNumber = curDraftRound?.pick_number || 0;
  const pickAlreadyMade = !!curDraftRound?.choice;

  useEffect(() => {
    // TODO: Add any side effects here if needed
  }, [curDraftRound?.pk, curDraftRound?.choice, curDraftRound?.captain?.pk]);

  if (pickAlreadyMade) {
    return (
      <div className="p-4 rounded-lg text-center bg-base-200">
        <span className="text-sm text-base-content/70">
          Pick #{pickNumber} completed by {captainName}
        </span>
      </div>
    );
  }


  return (
    <div
      className={`p-4 rounded-lg text-center ${
        isMyTurn ? 'bg-green-800 animate-pulse' : 'bg-base-200'
      }`}
    >
      {isMyTurn ? (
        <span className="text-lg font-bold text-white">
          It's YOUR turn to pick! (Pick #{pickNumber})
        </span>
      ) : (
        <span className="text-base-content">
          Waiting for <strong>{captainName}</strong> to pick (Pick #{pickNumber}
          )
        </span>
      )}
    </div>
  );
};
