import { winRateTone } from './format';
import type { PlayerLeagueSummary } from './schemas';

export type LeagueStatsFilter = 'all' | 'high_winrate' | 'experienced' | 'new_players';

export const EXPERIENCED_GAMES = 10;

export function matchesLeagueFilter(
  filter: LeagueStatsFilter,
  summary: PlayerLeagueSummary | undefined,
  minGames: number,
): boolean {
  const games = summary?.games ?? 0;
  switch (filter) {
    case 'all':
      return true;
    case 'high_winrate':
      return summary?.rank != null && winRateTone(summary.win_rate) === 'good';
    case 'experienced':
      return games >= EXPERIENCED_GAMES;
    case 'new_players':
      return games < minGames;
  }
}
