import { useEffect } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
const log = getLogger('liveView');
interface LiveViewProps {
  isPolling: boolean;
}

export const LiveView: React.FC<LiveViewProps> = ({ isPolling }) => {
  const tournament = useUserStore((state) => state.tournament);
  useEffect(() => {}, [isPolling]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold">Draft Progress</h3>
          {tournament?.draft?.pk && (
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  isPolling ? 'bg-success animate-pulse' : 'bg-warning'
                }`}
              />
              <span className="text-xs text-base-content/70">
                {isPolling ? 'Live updates' : 'Manual refresh only'}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
