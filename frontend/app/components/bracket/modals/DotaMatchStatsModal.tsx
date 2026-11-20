// frontend/app/components/bracket/modals/DotaMatchStatsModal.tsx
import { ScrollArea } from '@radix-ui/react-scroll-area';
import { ExternalLink } from 'lucide-react';
import type { MouseEvent } from 'react';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Skeleton } from '~/components/ui/skeleton';
import { useMatchStats } from '~/hooks/useMatchStats';
import { openExternal } from '~/lib/discord';
import {
  formatDuration,
  formatMatchDate,
  splitPlayersByTeam,
} from '~/lib/dota/utils';
import { cn } from '~/lib/utils';
import { PlayerStatsTable } from './PlayerStatsTable';

interface DotaMatchStatsModalProps {
  open: boolean;
  onClose: () => void;
  matchId: number | null;
  embedded?: boolean;
}

export function DotaMatchStatsModal({
  open,
  onClose,
  matchId,
  embedded = false,
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
            <MatchStatsContent matchId={matchId} embedded={embedded} />
          ) : (
            <MatchStatsSkeleton />
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function MatchStatsContent({
  matchId,
  embedded,
}: {
  matchId: number;
  embedded: boolean;
}) {
  const { data: match, isLoading, error } = useMatchStats(matchId);

  if (isLoading) return <MatchStatsSkeleton />;
  if (error) return <MatchStatsError error={error} />;
  if (!match) return <MatchStatsError error={new Error('Match not found')} />;

  const { radiant, dire } = splitPlayersByTeam(match.players);
  const radiantTotals = calculateTeamTotals(radiant);
  const direTotals = calculateTeamTotals(dire);
  const dotabuffUrl = `https://www.dotabuff.com/matches/${match.match_id}`;
  const opendotaUrl = `https://www.opendota.com/matches/${match.match_id}`;
  const openInDiscord = (url: string) => (event: MouseEvent) => {
    if (!embedded) return;
    event.preventDefault();
    void openExternal(url);
  };

  return (
    <div className="space-y-4">
      {/* Match header with external links */}
      <div className="flex items-start justify-between">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <a
              href={dotabuffUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={openInDiscord(dotabuffUrl)}
            >
              {!embedded && (
                <img
                  src="https://cdn.brandfetch.io/idKrze_WBi/w/96/h/96/theme/dark/logo.png?c=1dxbfHSJFAPEGdCLU4o5B"
                  alt="Dotabuff"
                  className="size-4 mr-1"
                />
              )}
              Dotabuff
              <ExternalLink className="size-3 ml-1" />
            </a>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a
              href={opendotaUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={openInDiscord(opendotaUrl)}
            >
              {!embedded && (
                <img
                  src="https://raw.githubusercontent.com/odota/web/master/public/assets/images/logo.png"
                  alt="OpenDota"
                  className="size-4 mr-1"
                />
              )}
              OpenDota
              <ExternalLink className="size-3 ml-1" />
            </a>
          </Button>
        </div>
        <div className="text-center flex-1">
          <h2 className="text-lg font-semibold">Match {match.match_id}</h2>
          <p className="text-sm text-muted-foreground">
            {formatDuration(match.duration)} •{' '}
            {formatMatchDate(match.start_time)}
          </p>
        </div>
        <div className="w-[140px]" /> {/* Spacer for balance */}
      </div>

      {/* Match result */}
      <div
        className={cn(
          'text-center py-2 rounded-md font-semibold',
          match.radiant_win
            ? 'bg-radiant-surface/60 text-radiant'
            : 'bg-dire-surface/60 text-dire',
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
    { kills: 0, deaths: 0, assists: 0 },
  );
}
