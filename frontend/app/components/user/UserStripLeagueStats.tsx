import { memo, useState } from 'react';
import { RecentForm } from '~/components/league-stats/RecentForm';
import { StreakBadge } from '~/components/league-stats/StreakBadge';
import { Badge } from '~/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { formatWinRate, toneClass, winRateTone } from '~/features/league-stats/format';
import { usePlayerLeagueSummary } from '~/features/league-stats/queries';
import { cn } from '~/lib/utils';

interface UserStripLeagueStatsProps {
  leaguePk: number;
  userId: number;
}

export const UserStripLeagueStats = memo(
  ({ leaguePk, userId }: UserStripLeagueStatsProps) => {
    const { data } = usePlayerLeagueSummary(leaguePk, userId);
    const [tooltipArmed, setTooltipArmed] = useState(false);

    const summary = data?.summary;
    if (!data || !summary || summary.games === 0) return null;

    const { population, minGames } = data;
    const tone = winRateTone(summary.win_rate);
    const label =
      summary.rank != null
        ? `Rank ${summary.rank} of ${population} players with ≥${minGames} ticket games in this league`
        : `Needs ${minGames} games to be ranked (${summary.games} so far)`;

    const badge = (
      <Badge
        variant="outline"
        className="px-1.5 py-0 text-xs font-mono tabular-nums justify-start gap-0"
        onPointerEnter={tooltipArmed ? undefined : () => setTooltipArmed(true)}
      >
        <span
          data-testid="strip-league-stats-rank"
          className="inline-block w-[4ch] text-right"
        >
          {summary.rank != null ? `#${summary.rank}` : ''}
        </span>
        <span aria-hidden>{' · '}</span>
        <span className="inline-block w-[4ch] text-right">{`${summary.games}g`}</span>
        <span aria-hidden>{' · '}</span>
        <span
          className={cn(
            'inline-block w-[4ch] text-right',
            tone === 'bad'
              ? 'rounded-[2px] bg-destructive/25 text-foreground font-semibold'
              : toneClass[tone],
          )}
        >
          {formatWinRate(summary.win_rate)}
        </span>
      </Badge>
    );

    return (
      <div
        data-testid="strip-league-stats"
        role="img"
        aria-label={label}
        className="hidden @[30rem]:flex flex-col justify-center gap-0.5 shrink-0"
      >
        {tooltipArmed ? (
          <Tooltip>
            <TooltipTrigger asChild>{badge}</TooltipTrigger>
            <TooltipContent
              side="top"
              className="text-xs bg-popover text-popover-foreground"
            >
              <p className="font-semibold text-foreground">League ticket games</p>
              <p className="text-muted-foreground">{label}</p>
            </TooltipContent>
          </Tooltip>
        ) : (
          badge
        )}
        <div className="flex h-[14px] items-center gap-1">
          <RecentForm results={summary.recent} count={5} />
          <StreakBadge streak={summary.streak} />
        </div>
      </div>
    );
  },
);

UserStripLeagueStats.displayName = 'UserStripLeagueStats';
