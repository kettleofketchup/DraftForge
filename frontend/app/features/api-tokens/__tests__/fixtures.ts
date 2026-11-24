import type { ApiToken, ApiUsage, CreatedApiToken } from '../schemas';

export function apiToken(overrides: Partial<ApiToken> = {}): ApiToken {
  return {
    id: 1,
    name: 'MMR bot',
    prefix: 'abcd1234',
    user: { pk: 9, username: 'owner' },
    created_at: '2026-11-01T10:00:00Z',
    last_used_at: null,
    revoked_at: null,
    revoked_by: null,
    ...overrides,
  };
}

export function createdApiToken(
  overrides: Partial<CreatedApiToken> = {},
): CreatedApiToken {
  return { ...apiToken(), token: 'dfk_abcd1234_secretsecret', ...overrides };
}

export function apiUsage(overrides: Partial<ApiUsage> = {}): ApiUsage {
  return {
    since: '2026-10-25',
    days: 30,
    limits: { per_minute: 60, per_day: 5000 },
    users: [
      {
        user: { pk: 9, username: 'owner' },
        requests: 42,
        throttled: 3,
        days: [
          { date: '2026-11-23', requests: 12, throttled: 1 },
          { date: '2026-11-22', requests: 30, throttled: 2 },
        ],
      },
    ],
    ...overrides,
  };
}
