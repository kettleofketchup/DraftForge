import { FastForward, Radio } from 'lucide-react';
import { cn } from '~/lib/utils';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { Button } from '../ui/button';

interface LiveViewProps {
  isPolling: boolean;
}

/** Just the Live/Auto toggle buttons - for placing in header */
export const LiveAutoButtons: React.FC<{ isPolling: boolean }> = ({ isPolling }) => {
  const toggleLivePolling = useTournamentStore(
    (state) => state.toggleLivePolling,
  );
  const toggleAutoAdvance = useTournamentStore(
    (state) => state.toggleAutoAdvance,
  );
  const autoAdvance = useTournamentStore((state) => state.autoAdvance);

  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <Button
        onClick={() => toggleLivePolling()}
        variant={'outline'}
        size="sm"
        className={cn(
          'h-7 px-2 text-xs',
          isPolling
            ? 'secondary border-green-600 text-green-400'
            : 'bg-muted/50',
        )}
      >
        <Radio className={cn('h-3 w-3 mr-1', isPolling && 'animate-pulse')} />
        Live
      </Button>
      <Button
        onClick={() => toggleAutoAdvance()}
        variant={'outline'}
        size="sm"
        className={cn(
          'h-7 px-2 text-xs',
          autoAdvance
            ? 'bg-blue-900/50 border-blue-600 text-blue-400'
            : 'bg-muted/50',
        )}
      >
        <FastForward className="h-3 w-3 mr-1" />
        Auto
      </Button>
    </div>
  );
};

/** Just the Draft round indicator - for placing centered */
export const DraftRoundIndicator: React.FC = () => {
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);

  const totalRounds = draft?.draft_rounds?.length || 0;

  return (
    <div className="flex items-center gap-2 justify-center">
      <h3 className="text-base font-semibold">Draft</h3>
      {curDraftRound?.pick_number && (
        <span className="text-xs font-medium px-1.5 py-0.5 bg-primary/20 text-primary rounded">
          #{curDraftRound.pick_number}{totalRounds > 0 ? `/${totalRounds}` : ''}
        </span>
      )}
    </div>
  );
};

/** Combined view (legacy) - kept for backwards compatibility */
export const LiveView: React.FC<LiveViewProps> = ({ isPolling }) => {
  return (
    <div className="flex flex-wrap items-center gap-2 justify-between overflow-visible py-1 pr-1">
      <DraftRoundIndicator />
      <LiveAutoButtons isPolling={isPolling} />
    </div>
  );
};
