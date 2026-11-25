import type { BotAccessRow, BotAccessSnapshot } from '../schemas';

export function makeRow(overrides: Partial<BotAccessRow> = {}): BotAccessRow {
  return {
    position: 1,
    identity: {
      kind: 'steam',
      value: '76561197960265729',
      profile_url: 'https://steamcommunity.com/profiles/76561197960265729',
    },
    status: 'available',
    access: 'verified',
    access_note: null,
    access_checked_at: '2026-11-24T12:00:00Z',
    refresh: null,
    ...overrides,
  };
}

export function makeSnapshot(
  overrides: Partial<BotAccessSnapshot> = {},
): BotAccessSnapshot {
  return {
    game_type: 1,
    supported: true,
    provider: 'dota2',
    external_league_id: '12345',
    service: { status: 'ok', code: null, retryable: false },
    bots: [
      makeRow(),
      makeRow({
        position: 2,
        identity: {
          kind: 'steam',
          value: '76561197960265730',
          profile_url: 'https://steamcommunity.com/profiles/76561197960265730',
        },
        status: 'busy',
        access: 'missing',
        access_checked_at: null,
      }),
    ],
    held_count: 1,
    league_link: {
      kind: 'league_admin_portal',
      url: 'https://www.dota2.com/league/12345/admins',
    },
    refresh_outcome: null,
    roster: 'all',
    checked_at: '2026-11-24T12:00:00Z',
    ...overrides,
  };
}
