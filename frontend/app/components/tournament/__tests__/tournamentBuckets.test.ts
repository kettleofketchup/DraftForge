import { describe, expect, it } from 'vitest';

import type { TournamentType } from '../types';
import {
  bucketCutoff,
  clockBucket,
  cutoffDayKey,
  dedupeByPk,
  displayState,
  filtersActive,
  isTournamentLive,
  leagueId,
  leagueInfo,
  normalizeSearch,
  parseFilterId,
  splitByMembership,
  utcDayStart,
} from '../tournamentBuckets';

const NOW = new Date('2026-11-13T15:00:00Z');

function make(overrides: Partial<TournamentType> = {}): TournamentType {
  return {
    name: 'T',
    date_played: '2026-11-20T18:00:00Z',
    timezone: 'UTC',
    pk: 1,
    state: 'future',
    tournament_type: 'single_elimination',
    league: null,
    auto_create_hero_drafts: false,
    discord_send_draft_link: false,
    discord_send_herodraft_link: false,
    dota_lobby_mode: 'off',
    dota_lobby_launch: 'manual',
    dota_lobby_region: '',
    discord_send_lobby_info: false,
    ...overrides,
  };
}

function withOrg(pk: number, organizationId: number | null): TournamentType {
  return make({
    pk,
    league: { pk: 100 + pk, name: 'L', organization_name: 'O', organization_id: organizationId },
  });
}

describe('cutoff', () => {
  it('starts the UTC day', () => {
    expect(utcDayStart(NOW).toISOString()).toBe('2026-11-13T00:00:00.000Z');
  });

  it('is midnight UTC two days before today', () => {
    expect(bucketCutoff(NOW).toISOString()).toBe('2026-11-11T00:00:00.000Z');
  });

  it('keys by the cutoff day', () => {
    expect(cutoffDayKey(NOW)).toBe('2026-11-11');
  });
});

describe('clockBucket', () => {
  it('puts a future tournament on the cutoff in upcoming', () => {
    expect(clockBucket(make({ date_played: '2026-11-11T00:00:00Z' }), NOW)).toBe('upcoming');
  });

  it('puts a future tournament before the cutoff in archived', () => {
    expect(clockBucket(make({ date_played: '2026-11-10T23:59:59Z' }), NOW)).toBe('archived');
  });

  it('puts an undated tournament in archived', () => {
    expect(clockBucket(make({ date_played: null }), NOW)).toBe('archived');
  });

  it('puts a past tournament in archived', () => {
    expect(clockBucket(make({ state: 'past' }), NOW)).toBe('archived');
  });
});

describe('displayState without a bucket', () => {
  it('shows Live for an in-progress tournament today', () => {
    const t = make({ state: 'in_progress', date_played: '2026-11-13T12:00:00Z' });
    expect(displayState(t, NOW)).toEqual({ label: 'Live', muted: false });
    expect(isTournamentLive(t, NOW)).toBe(true);
  });

  it('shows Awaiting results inside the grace window', () => {
    const t = make({ date_played: '2026-11-12T12:00:00Z' });
    expect(displayState(t, NOW)).toEqual({ label: 'Awaiting results', muted: true });
  });

  it('shows Upcoming for a future date', () => {
    expect(displayState(make(), NOW)).toEqual({ label: 'Upcoming', muted: false });
  });

  it('shows Past for a past tournament', () => {
    const t = make({ state: 'past', date_played: '2026-10-01T12:00:00Z' });
    expect(displayState(t, NOW)).toEqual({ label: 'Past', muted: false });
  });

  it('shows Past (not closed) for a stale future tournament', () => {
    const t = make({ date_played: '2026-11-10T23:59:59Z' });
    expect(displayState(t, NOW)).toEqual({ label: 'Past (not closed)', muted: true });
  });

  it('shows Past (not closed) and not live for a stale in-progress tournament', () => {
    const t = make({ state: 'in_progress', date_played: '2026-11-01T12:00:00Z' });
    expect(displayState(t, NOW)).toEqual({ label: 'Past (not closed)', muted: true });
    expect(isTournamentLive(t, NOW)).toBe(false);
  });

  it('shows Past (not closed) for an unknown state', () => {
    const t = make({ state: 'ongoing' as never });
    expect(displayState(t, NOW)).toEqual({ label: 'Past (not closed)', muted: true });
  });
});

describe('displayState with a bucket', () => {
  it('never shows Past* for an upcoming row', () => {
    const t = make({ date_played: '2026-11-10T12:00:00Z' });
    expect(displayState(t, NOW, 'upcoming')).toEqual({ label: 'Awaiting results', muted: true });
  });

  it('always shows Live for an in-progress upcoming row', () => {
    const t = make({ state: 'in_progress', date_played: '2026-11-01T12:00:00Z' });
    expect(displayState(t, NOW, 'upcoming')).toEqual({ label: 'Live', muted: false });
    expect(isTournamentLive(t, NOW, 'upcoming')).toBe(true);
  });

  it('never shows Live for an archived row', () => {
    const t = make({ state: 'in_progress', date_played: '2026-11-13T12:00:00Z' });
    expect(displayState(t, NOW, 'archived')).toEqual({ label: 'Past (not closed)', muted: true });
    expect(isTournamentLive(t, NOW, 'archived')).toBe(false);
  });
});

describe('league accessors', () => {
  const league = { pk: 3, name: 'L', organization_name: 'O' };

  it('returns the league object', () => {
    expect(leagueInfo(make({ league }))).toEqual(league);
  });

  it('returns null for a numeric league', () => {
    expect(leagueInfo(make({ league: 7 }))).toBeNull();
  });

  it('returns null for a missing league', () => {
    expect(leagueInfo(make({ league: null }))).toBeNull();
    expect(leagueInfo(make({ league: undefined }))).toBeNull();
  });

  it('reads the league id from either shape', () => {
    expect(leagueId(make({ league }))).toBe(3);
    expect(leagueId(make({ league: 7 }))).toBe(7);
    expect(leagueId(make({ league: null }))).toBeNull();
  });
});

describe('splitByMembership', () => {
  it('splits by organization and preserves order', () => {
    const a = withOrg(1, 1);
    const b = withOrg(2, 2);
    const c = withOrg(3, null);
    const d = make({ pk: 4, league: 7 });
    const e = withOrg(5, 1);
    expect(splitByMembership([a, b, c, d, e], [1])).toEqual({ yours: [a, e], others: [b, c, d] });
  });

  it('treats undefined ids as no memberships', () => {
    const a = withOrg(1, 1);
    expect(splitByMembership([a], undefined)).toEqual({ yours: [], others: [a] });
  });
});

describe('normalizeSearch', () => {
  it('ignores blank and one-character input', () => {
    expect(normalizeSearch(' ')).toBeUndefined();
    expect(normalizeSearch('a')).toBeUndefined();
  });

  it('trims', () => {
    expect(normalizeSearch(' ab ')).toBe('ab');
  });

  it('truncates to 64 characters', () => {
    expect(normalizeSearch('x'.repeat(70))).toHaveLength(64);
  });
});

describe('dedupeByPk', () => {
  it('keeps the first occurrence of each pk', () => {
    const first = make({ pk: 1, name: 'first' });
    const second = make({ pk: 2 });
    const dup = make({ pk: 1, name: 'dup' });
    expect(dedupeByPk([first, second, dup])).toEqual([first, second]);
  });
});

describe('parseFilterId', () => {
  it('rejects non-positive or non-numeric values', () => {
    for (const raw of ['abc', '0', '-3', '12abc', '', null]) {
      expect(parseFilterId(raw)).toBeUndefined();
    }
  });

  it('parses a positive integer', () => {
    expect(parseFilterId('12')).toBe(12);
  });
});

describe('filtersActive', () => {
  it('ignores a search too short to send', () => {
    expect(filtersActive({ searchInput: 'a' })).toBe(false);
  });

  it('counts an organization filter', () => {
    expect(filtersActive({ organization: 3, searchInput: '' })).toBe(true);
  });

  it('counts a league filter and a real search', () => {
    expect(filtersActive({ league: 4, searchInput: '' })).toBe(true);
    expect(filtersActive({ searchInput: 'ab' })).toBe(true);
  });
});
