import { motion } from 'framer-motion';
import { ToggleLeft, ToggleRight } from 'lucide-react';
import { useEffect } from 'react';
import { getLogger } from '~/lib/logger';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { Button } from '../ui/button';
const log = getLogger('liveView');
interface LiveViewProps {
  isPolling: boolean;
}

export const LiveView: React.FC<LiveViewProps> = ({ isPolling }) => {
  const tournament = useUserStore((state) => state.tournament);
  const toggleAutoAdvance = useTournamentStore(
    (state) => state.toggleAutoAdvance,
  );
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);
  useEffect(() => {}, [isPolling, autoAdvance]);
  const autoAdvanceButtonClick = () => {
    toggleAutoAdvance();
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center flex-col sm:flex-row gap-2 justify-between sm:justify-start">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold">Draft Progress</h3>{' '}
        </div>

        {tournament?.draft?.pk && (
          <div className="flex items-center gap-2 align-middle">
            <div
              className={`w-2 h-2 rounded-full ${
                isPolling ? 'w-2 bg-success animate-pulse' : 'bg-warning'
              }`}
            />
            <span className="w-[10em] text-xs text-base-content/70">
              {isPolling ? 'Live updates' : 'Manual refresh only'}
            </span>
          </div>
        )}
        <motion.div
          initial={{ scale: 1 }}
          animate={{
            scale: autoAdvance ? 1 : 1,
          }}
          whileTap={{
            opacity: 0,
            transition: { duration: 0.5, ease: 'easeInOut' },
          }}
        >
          <Button
            onClick={autoAdvanceButtonClick}
            variant={'outline'}
            className="rounded-full"
          >
            {autoAdvance ? <ToggleLeft /> : <ToggleRight />}
            Auto Advance: {isPolling ? 'ON' : 'OFF'}
          </Button>
        </motion.div>
      </div>
    </div>
  );
};
