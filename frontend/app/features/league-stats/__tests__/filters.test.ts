import { describe, expect, it } from 'vitest';
import { matchesLeagueFilter } from '../filters';
import type { PlayerLeagueSummary } from '../schemas';

function summary(games: number, winRate: number, rank: number | null): PlayerLeagueSummary {
  return { games, win_rate: winRate, rank } as PlayerLeagueSummary;
}

describe('matchesLeagueFilter', () => {
  it('all keeps everyone, including players without ticket games', () => {
    expect(matchesLeagueFilter('all', undefined, 5)).toBe(true);
    expect(matchesLeagueFilter('all', summary(3, 0.2, null), 5)).toBe(true);
  });

  it('high_winrate keeps ranked players at a rounded 55% or more', () => {
    expect(matchesLeagueFilter('high_winrate', summary(20, 0.55, 3), 5)).toBe(true);
    expect(matchesLeagueFilter('high_winrate', summary(20, 0.546, 3), 5)).toBe(true);
    expect(matchesLeagueFilter('high_winrate', summary(20, 0.544, 3), 5)).toBe(false);
  });

  it('high_winrate drops unranked players however well they did', () => {
    expect(matchesLeagueFilter('high_winrate', summary(2, 1, null), 5)).toBe(false);
    expect(matchesLeagueFilter('high_winrate', undefined, 5)).toBe(false);
  });

  it('experienced keeps players with 10 or more ticket games', () => {
    expect(matchesLeagueFilter('experienced', summary(10, 0.4, 9), 5)).toBe(true);
    expect(matchesLeagueFilter('experienced', summary(9, 0.9, 1), 5)).toBe(false);
    expect(matchesLeagueFilter('experienced', undefined, 5)).toBe(false);
  });

  it('new_players keeps players below the ranking threshold, including none', () => {
    expect(matchesLeagueFilter('new_players', undefined, 5)).toBe(true);
    expect(matchesLeagueFilter('new_players', summary(4, 0.5, null), 5)).toBe(true);
    expect(matchesLeagueFilter('new_players', summary(5, 0.5, 4), 5)).toBe(false);
    expect(matchesLeagueFilter('new_players', summary(3, 0.5, 2), 3)).toBe(false);
  });
});
