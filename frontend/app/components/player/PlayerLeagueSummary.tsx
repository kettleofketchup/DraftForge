import type React from 'react';
import { useEffect } from 'react';
import { RecentForm } from '~/components/league-stats/RecentForm';
import { WinRateHistogram } from '~/components/league-stats/WinRateHistogram';
import { LeagueStatsHttpError, useUserLeagueStatsByLeague } from '~/features/leaderboard/queries';
import { formatWinRate, toneClass, winRateTone } from '~/features/league-stats/format';
import { useLeagueDistribution, usePlayerLeagueSummary } from '~/features/league-stats/queries';
import type { LeagueStatsResponse, PlayerLeagueSummary as Summary } from '~/features/league-stats/schemas';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';

const log = getLogger('league-stats');

const PANEL_FORM_COUNT = 10;

const Tile: React.FC<{
  label: string;
  value: React.ReactNode;
  caption: React.ReactNode;
  valueClassName?: string;
  compact?: boolean;
}> = ({ label, value, caption, valueClassName, compact = false }) => (
  <div className={cn('rounded-md bg-muted/40', compact ? 'px-2 py-1.5' : 'px-3 py-2')}>
    <div className="text-xs text-muted-foreground">{label}</div>
    <div
      className={cn(
        'font-bold tabular-nums',
        compact ? 'text-base whitespace-nowrap' : 'text-xl',
        valueClassName,
      )}
    >
      {value}
    </div>
    <div className="text-xs text-muted-foreground">{caption}</div>
  </div>
);

function streakCaption(streak: Summary['streak']): string {
  if (!streak) return 'no games yet';
  const verb = streak.result === 'W' ? 'won' : 'lost';
  return streak.count === 1 ? `${verb} last game` : `${verb} last ${streak.count}`;
}

const fmt1 = (n: number): string => n.toFixed(1);

function averagesLine(stats: LeagueStatsResponse): string {
  return `KDA ${fmt1(stats.avg_kills)} / ${fmt1(stats.avg_deaths)} / ${fmt1(stats.avg_assists)} · GPM ${Math.round(stats.avg_gpm)} · XPM ${Math.round(stats.avg_xpm)}`;
}

export const PlayerLeagueSummary: React.FC<{
  leaguePk: number;
  userId: number;
  /** Hover-card variant: no KDA/GPM/XPM averages line and no request for it. */
  compact?: boolean;
}> = ({ leaguePk, userId, compact = false }) => {
  const summaryQuery = usePlayerLeagueSummary(leaguePk, userId);
  const distributionQuery = useLeagueDistribution(leaguePk);
  const statsQuery = useUserLeagueStatsByLeague(compact ? undefined : userId, leaguePk);

  const summaryError = summaryQuery.error;
  const statsError = statsQuery.error;

  useEffect(() => {
    if (!summaryError) return;
    log.error('league summary failed to load', { leaguePk, userId, error: summaryError });
  }, [summaryError, leaguePk, userId]);

  useEffect(() => {
    if (!statsError) return;
    log.error('league averages failed to load', {
      leaguePk,
      userId,
      status: statsError instanceof LeagueStatsHttpError ? statsError.status : undefined,
      error: statsError,
    });
  }, [statsError, leaguePk, userId]);

  const averages = compact ? null : statsQuery.isPending ? (
    <div className="text-xs text-muted-foreground">Loading averages...</div>
  ) : statsQuery.isError ? (
    <div className="text-xs text-muted-foreground">Averages unavailable</div>
  ) : statsQuery.data ? (
    <div className="text-xs text-muted-foreground tabular-nums">
      {averagesLine(statsQuery.data)}
    </div>
  ) : null;

  if (summaryQuery.isPending) {
    return <div className="text-sm text-muted-foreground">Loading stats...</div>;
  }

  if (summaryQuery.isError || distributionQuery.isError) {
    return (
      <div className="space-y-1">
        <div className="text-sm text-muted-foreground">Couldn't load league stats</div>
        {statsQuery.isSuccess ? averages : null}
      </div>
    );
  }

  const { summary, population, minGames } = summaryQuery.data;
  if (!summary || summary.games === 0) {
    return <div className="text-sm text-muted-foreground">No league stats available</div>;
  }

  const ranked = summary.rank != null;
  const tone = winRateTone(summary.win_rate);

  return (
    <div data-testid={compact ? 'hover-league-summary' : 'player-league-summary'} className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile compact={compact}
          label="Rank"
          value={`${ranked ? `#${summary.rank}` : '—'} / ${population}`}
          caption={
            ranked ? `top ${summary.top_percent}%` : `${summary.games}/${minGames} games to rank`
          }
        />
        <Tile compact={compact} label="Games" value={summary.games} caption="ticket games" />
        <Tile compact={compact}
          label="Win rate"
          value={formatWinRate(summary.win_rate)}
          valueClassName={toneClass[tone]}
          caption={`${summary.wins}–${summary.losses}`}
        />
        <Tile compact={compact}
          label="Streak"
          value={summary.streak ? `${summary.streak.result}${summary.streak.count}` : '—'}
          caption={streakCaption(summary.streak)}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Recent</span>
        <RecentForm results={summary.recent} count={PANEL_FORM_COUNT} />
        <span className="text-xs text-muted-foreground">{`last ${PANEL_FORM_COUNT}, oldest → newest`}</span>
      </div>

      {distributionQuery.data && (
        <WinRateHistogram
          distribution={distributionQuery.data.distribution}
          population={distributionQuery.data.population}
          minGames={distributionQuery.data.minGames}
          highlightBucket={summary.bucket}
        />
      )}

      {averages}
    </div>
  );
};
