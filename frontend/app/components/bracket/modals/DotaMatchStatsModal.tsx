// frontend/app/components/bracket/modals/DotaMatchStatsModal.tsx
import { ScrollArea } from '@radix-ui/react-scroll-area';
import { ExternalLink } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '~/components/ui/dialog';
import { Button } from '~/components/ui/button';
import { Skeleton } from '~/components/ui/skeleton';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { useMatchStats } from '~/hooks/useMatchStats';
import {
  splitPlayersByTeam,
  formatDuration,
  formatMatchDate,
} from '~/lib/dota/utils';
import { PlayerStatsTable } from './PlayerStatsTable';
import { cn } from '~/lib/utils';

interface DotaMatchStatsModalProps {
  open: boolean;
  onClose: () => void;
  matchId: number | null;
}

export function DotaMatchStatsModal({
  open,
  onClose,
  matchId,
}: DotaMatchStatsModalProps) {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className={DIALOG_CSS}>
        <ScrollArea className={SCROLLAREA_CSS}>
          <DialogHeader>
            <DialogTitle className="sr-only">Match Statistics</DialogTitle>
            <DialogDescription className="sr-only">
              Detailed statistics for this Dota 2 match
            </DialogDescription>
          </DialogHeader>
          {matchId ? (
            <MatchStatsContent matchId={matchId} />
          ) : (
            <MatchStatsSkeleton />
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function MatchStatsContent({ matchId }: { matchId: number }) {
  const { data: match, isLoading, error } = useMatchStats(matchId);

  if (isLoading) return <MatchStatsSkeleton />;
  if (error) return <MatchStatsError error={error} />;
  if (!match) return <MatchStatsError error={new Error('Match not found')} />;

  const { radiant, dire } = splitPlayersByTeam(match.players);
  const radiantTotals = calculateTeamTotals(radiant);
  const direTotals = calculateTeamTotals(dire);

  return (
    <div className="space-y-4">
      {/* Match header with external links */}
      <div className="flex items-start justify-between">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            asChild
          >
            <a
              href={`https://www.dotabuff.com/matches/${match.match_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Dotabuff
              <ExternalLink className="w-3 h-3 ml-1" />
            </a>
          </Button>
          <Button
            variant="outline"
            size="sm"
            asChild
          >
            <a
              href={`https://www.opendota.com/matches/${match.match_id}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              OpenDota
              <ExternalLink className="w-3 h-3 ml-1" />
            </a>
          </Button>
        </div>
        <div className="text-center flex-1">
          <h2 className="text-lg font-semibold">Match {match.match_id}</h2>
          <p className="text-sm text-muted-foreground">
            {formatDuration(match.duration)} • {formatMatchDate(match.start_time)}
          </p>
        </div>
        <div className="w-[140px]" /> {/* Spacer for balance */}
      </div>

      {/* Match result */}
      <div
        className={cn(
          'text-center py-2 rounded-md font-semibold',
          match.radiant_win
            ? 'bg-green-900/50 text-green-400'
            : 'bg-red-900/50 text-red-400'
        )}
      >
        {match.radiant_win ? 'Radiant Victory' : 'Dire Victory'}
      </div>

      {/* Radiant team */}
      <PlayerStatsTable
        players={radiant}
        team="radiant"
        isWinner={match.radiant_win}
        teamTotals={radiantTotals}
      />

      {/* Dire team */}
      <PlayerStatsTable
        players={dire}
        team="dire"
        isWinner={!match.radiant_win}
        teamTotals={direTotals}
      />
    </div>
  );
}

function MatchStatsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48 mx-auto" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-64 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function MatchStatsError({ error }: { error: Error }) {
  return (
    <div className="text-center py-8">
      <p className="text-destructive">Failed to load match stats</p>
      <p className="text-sm text-muted-foreground">{error.message}</p>
    </div>
  );
}

interface PlayerStats {
  kills: number;
  deaths: number;
  assists: number;
}

function calculateTeamTotals(players: PlayerStats[]) {
  return players.reduce(
    (acc, player) => ({
      kills: acc.kills + player.kills,
      deaths: acc.deaths + player.deaths,
      assists: acc.assists + player.assists,
    }),
    { kills: 0, deaths: 0, assists: 0 }
  );
}
