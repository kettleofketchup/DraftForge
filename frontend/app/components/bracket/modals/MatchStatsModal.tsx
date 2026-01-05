// frontend/app/components/bracket/modals/MatchStatsModal.tsx
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Skeleton } from '~/components/ui/skeleton';
import { useMatchStats } from '~/hooks/useMatchStats';
import {
  splitPlayersByTeam,
  formatDuration,
  formatMatchDate,
} from '~/lib/dota/utils';
import { PlayerStatsTable } from './PlayerStatsTable';
import { cn } from '~/lib/utils';

interface MatchStatsModalProps {
  open: boolean;
  onClose: () => void;
  matchId: number | null;
}

export function MatchStatsModal({
  open,
  onClose,
  matchId,
}: MatchStatsModalProps) {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        {matchId ? (
          <MatchStatsContent matchId={matchId} />
        ) : (
          <MatchStatsSkeleton />
        )}
      </DialogContent>
    </Dialog>
  );
}

function MatchStatsContent({ matchId }: { matchId: number }) {
  const { data: match, isLoading, error } = useMatchStats(matchId);

  if (isLoading) {
    return <MatchStatsSkeleton />;
  }

  if (error || !match) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Failed to load match data
      </div>
    );
  }

  const { radiant, dire } = splitPlayersByTeam(match.players);

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center justify-between">
          <span>Match {match.match_id}</span>
          <span className="text-sm font-normal text-muted-foreground">
            {formatDuration(match.duration)} •{' '}
            {formatMatchDate(match.start_time)}
          </span>
        </DialogTitle>
      </DialogHeader>

      {/* Result Banner */}
      <div
        className={cn(
          'text-center py-3 rounded-md font-semibold text-lg',
          match.radiant_win
            ? 'bg-green-900/40 text-green-300'
            : 'bg-red-900/40 text-red-300'
        )}
      >
        {match.radiant_win ? 'Radiant Victory' : 'Dire Victory'}
      </div>

      {/* Team Tables */}
      <div className="space-y-6">
        <PlayerStatsTable
          players={radiant}
          team="Radiant"
          isWinner={match.radiant_win}
        />
        <PlayerStatsTable
          players={dire}
          team="Dire"
          isWinner={!match.radiant_win}
        />
      </div>
    </>
  );
}

function MatchStatsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
