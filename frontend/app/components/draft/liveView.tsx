import { Radio, FastForward } from 'lucide-react';
import { cn } from '~/lib/utils';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { Button } from '../ui/button';

interface LiveViewProps {
  isPolling: boolean;
}

export const LiveView: React.FC<LiveViewProps> = ({ isPolling }) => {
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const toggleLivePolling = useTournamentStore(
    (state) => state.toggleLivePolling,
  );
  const toggleAutoAdvance = useTournamentStore(
    (state) => state.toggleAutoAdvance,
  );
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);

  const livePollingButtonClick = () => {
    toggleLivePolling();
  };
  const autoAdvanceButtonClick = () => {
    toggleAutoAdvance();
  };

  return (
    <div className="flex flex-wrap items-center gap-2 justify-between">
      {/* Left side: Title, pick number */}
      <div className="flex items-center gap-2">
        <h3 className="text-base font-semibold">Draft</h3>
        {curDraftRound?.pick_number && (
          <span className="text-xs font-medium px-1.5 py-0.5 bg-primary/20 text-primary rounded">
            #{curDraftRound.pick_number}
          </span>
        )}
      </div>

      {/* Right side: Toggle buttons */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <Button
          onClick={livePollingButtonClick}
          variant={'outline'}
          size="sm"
          className={cn(
            'h-8 px-3 text-xs',
            isPolling
              ? 'bg-green-900/50 border-green-600 text-green-400'
              : 'bg-muted/50'
          )}
        >
          <Radio className={cn('h-3 w-3 mr-1', isPolling && 'animate-pulse')} />
          Live
        </Button>
        <Button
          onClick={autoAdvanceButtonClick}
          variant={'outline'}
          size="sm"
          className={cn(
            'h-8 px-3 text-xs',
            autoAdvance
              ? 'bg-blue-900/50 border-blue-600 text-blue-400'
              : 'bg-muted/50'
          )}
        >
          <FastForward className="h-3 w-3 mr-1" />
          Auto
        </Button>
      </div>
    </div>
  );
};
