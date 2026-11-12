import { memo } from 'react';
import { RecentForm } from '~/components/league-stats/RecentForm';
import { PlayerPopoverTrigger as PlayerPopover } from '~/components/player/PlayerPopoverTrigger';
import { MIN_STREAK, StreakBadge } from '~/components/league-stats/StreakBadge';
import { Badge } from '~/components/ui/badge';
import { formatWinRate, toneChipClass, winRateTone } from '~/features/league-stats/format';
import { usePlayerLeagueSummary } from '~/features/league-stats/queries';
import type { PlayerLeagueSummary } from '~/features/league-stats/schemas';
import { cn } from '~/lib/utils';
import type { UserEntry } from '~/store/userCacheTypes';
import type { UserType } from './types';

const FORM_COUNT = 5;

function accessibleLabel(
  summary: PlayerLeagueSummary,
  population: number,
  minGames: number,
): string {
  const recent = summary.recent.slice(-FORM_COUNT);
  const parts = [
    summary.rank != null
      ? `Rank ${summary.rank} of ${population} (≥${minGames} ticket games), ${summary.games} ${summary.games === 1 ? 'game' : 'games'}`
      : `Unranked: needs ${minGames} ticket games (${summary.games} so far)`,
    `${formatWinRate(summary.win_rate)} win rate`,
  ];
  if (recent.length > 0) {
    parts.push(`last ${recent.length}: ${recent.join(' ')}, oldest to newest`);
  }
  if (summary.streak && summary.streak.count >= MIN_STREAK) {
    parts.push(`${summary.streak.result === 'W' ? 'win' : 'loss'} streak ${summary.streak.count}`);
  }
  return parts.join(', ');
}

export type StatsBreakpoint = 'default' | 'wide';

const breakpointClass: Record<StatsBreakpoint, string> = {
  default: '@[30rem]:flex',
  wide: '@[44rem]:flex',
};

interface UserStripLeagueStatsProps {
  leaguePk: number;
  player: UserType | UserEntry;
  breakpoint?: StatsBreakpoint;
}

export const UserStripLeagueStats = memo(
  ({ leaguePk, player, breakpoint = 'default' }: UserStripLeagueStatsProps) => {
    const { data } = usePlayerLeagueSummary(leaguePk, player.pk ?? -1);

    const summary = data?.summary;
    if (!data || !summary || summary.games === 0) return null;

    const { population, minGames } = data;
    const tone = winRateTone(summary.win_rate);
    const playerName = player.nickname || player.username || 'Unknown';
    const label = `League stats for ${playerName}: ${accessibleLabel(summary, population, minGames)}. Opens the player panel`;

    return (
      <div
        data-testid="strip-league-stats"
        className={cn('hidden shrink-0', breakpointClass[breakpoint])}
      >
        <PlayerPopover
          player={player as UserType}
          statsLeagueId={leaguePk}
          label={label}
          className="flex flex-col justify-center gap-0.5"
        >
          <Badge
            variant="outline"
            className="px-1.5 py-0 text-xs font-mono tabular-nums justify-start gap-0 hover:bg-muted/50"
          >
            <span
              data-testid="strip-league-stats-rank"
              className="inline-block min-w-[4ch] text-right"
            >
              {summary.rank != null ? `#${summary.rank}` : ''}
            </span>
            <span aria-hidden className="whitespace-pre">{' · '}</span>
            <span className="inline-block min-w-[4ch] text-right">{`${summary.games}g`}</span>
            <span aria-hidden className="whitespace-pre">{' · '}</span>
            <span className={cn('inline-block min-w-[4ch] text-right', toneChipClass[tone])}>
              {formatWinRate(summary.win_rate)}
            </span>
          </Badge>
          <span className="flex h-[14px] items-center gap-1">
            <RecentForm results={summary.recent} count={FORM_COUNT} />
            <StreakBadge streak={summary.streak} />
          </span>
        </PlayerPopover>
      </div>
    );
  },
);

UserStripLeagueStats.displayName = 'UserStripLeagueStats';
