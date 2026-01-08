import { useUserStore } from '~/store/userStore';

/**
 * Indicator showing whose turn it is in the draft.
 *
 * Displays a prominent message when it's the current user's turn,
 * or shows which captain is currently picking.
 */
export const TurnIndicator: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

  const isMyTurn = currentUser?.pk === curDraftRound?.captain?.pk;
  const captainName = curDraftRound?.captain?.nickname || curDraftRound?.captain?.username || 'Unknown';
  const pickNumber = curDraftRound?.pick_number || 0;
  const pickAlreadyMade = !!curDraftRound?.choice;

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
