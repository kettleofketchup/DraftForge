import { DisplayName } from '~/components/user/avatar';
import { draftWsSelectors, useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useUserStore } from '~/store/userStore';

export const TurnIndicator: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const activeRoundPk = useDraftWebSocketStore(draftWsSelectors.activeRoundPk);
  const timerEnabled = useDraftWebSocketStore(draftWsSelectors.timerEnabled);

  const captainName = curDraftRound?.captain ? DisplayName(curDraftRound.captain) : 'Unknown';
  const pickNumber = curDraftRound?.pick_number || 0;
  const isActiveRound = !timerEnabled || curDraftRound?.pk === activeRoundPk;
  const isMyTurn =
    currentUser?.pk != null && currentUser.pk === curDraftRound?.captain?.pk && isActiveRound;

  if (curDraftRound?.choice) {
    return (
      <div className="p-4 rounded-lg text-center bg-base-200">
        <span className="text-sm text-base-content/70">
          Pick #{pickNumber} completed by {captainName}
        </span>
      </div>
    );
  }

  const deferred = timerEnabled && !isActiveRound && (curDraftRound?.skip_count ?? 0) > 0;
  if (deferred) {
    return (
      <div data-testid="turn-indicator-deferred" className="p-4 rounded-lg text-center bg-base-200">
        <span className="text-base-content">
          Pick #{pickNumber} — deferred, {captainName} picks after #{pickNumber - 1}
        </span>
      </div>
    );
  }

  return (
    <div
      data-testid="turn-indicator"
      className={`p-4 rounded-lg text-center ${isMyTurn ? 'bg-green-800 animate-pulse' : 'bg-base-200'}`}
    >
      {isMyTurn ? (
        <span className="text-lg font-bold text-white">
          It's YOUR turn to pick! (Pick #{pickNumber})
        </span>
      ) : (
        <span className="text-base-content">
          Waiting for <strong>{captainName}</strong> to pick (Pick #{pickNumber})
        </span>
      )}
    </div>
  );
};
