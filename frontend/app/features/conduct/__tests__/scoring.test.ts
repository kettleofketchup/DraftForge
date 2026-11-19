import { describe, expect, it } from 'vitest';
import {
  ConductLeaderboardSchema,
  ConductSettingsFormSchema,
  type Forecast,
} from '../schemas';
import {
  formatForecast,
  formatOpenSeats,
  formatShowRate,
  scoreLabel,
} from '../scoring';

const member = {
  org_user_pk: 7,
  user_pk: 11,
  username: 'alice',
  nickname: null,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
};

const forecast: Forecast = {
  seat_holders: 30,
  expected: 24.2,
  low: 21,
  high: 27,
  waitlisted: 2,
  pending_approval: 0,
  capacity: 30,
  expected_open_seats: 5.8,
  new_members: 4,
  members: {},
};

describe('formatShowRate', () => {
  it('rounds to a whole percent', () => {
    expect(formatShowRate(0.793)).toBe('79%');
  });
});

describe('scoreLabel', () => {
  it('labels new members "New"', () => {
    expect(scoreLabel({ show_rate: 0.85, status: 'new' })).toBe('New');
  });

  it('shows the rate for scored members', () => {
    expect(scoreLabel({ show_rate: 0.85, status: 'scored' })).toBe('85%');
  });
});

describe('formatForecast', () => {
  it('uses the signed-up / expect / range format with an en dash', () => {
    expect(formatForecast(forecast)).toBe('30 signed up · expect ~24 (21–27)');
  });
});

describe('formatOpenSeats', () => {
  it('rounds the expected open seats', () => {
    expect(formatOpenSeats(forecast)).toBe('~6 open seats');
  });

  it('is null when capacity is unknown', () => {
    expect(
      formatOpenSeats({
        ...forecast,
        capacity: null,
        expected_open_seats: null,
      }),
    ).toBeNull();
  });
});

describe('ConductLeaderboardSchema', () => {
  it('parses a hidden-rows payload with an own row', () => {
    const parsed = ConductLeaderboardSchema.parse({
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: {
        member,
        show_rate: 0.85,
        counted_events: 0,
        status: 'new',
        rank: null,
      },
    });
    expect(parsed.rows_visible).toBe(false);
    expect(parsed.own_row?.member.org_user_pk).toBe(7);
  });
});

describe('ConductSettingsFormSchema', () => {
  const valid = {
    late_cancel_hours: 2,
    late_cancel_weight: 0.5,
    half_life_days: 90,
    max_age_days: 365,
    prior_show_rate: 0.85,
    prior_strength: 3,
    min_events: 3,
    leaderboard_public: true,
    back_of_line_enabled: false,
    back_of_line_below: 0.75,
    require_approval_enabled: false,
    require_approval_below: 0.65,
    block_enabled: false,
    block_below: 0.4,
    enforce_on_new_members: false,
  };

  it('accepts the defaults', () => {
    expect(ConductSettingsFormSchema.safeParse(valid).success).toBe(true);
  });

  it('refuses a max age below the half-life on max_age_days', () => {
    const result = ConductSettingsFormSchema.safeParse({
      ...valid,
      half_life_days: 200,
      max_age_days: 100,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(['max_age_days']);
  });

  it('refuses an out-of-range half-life', () => {
    expect(
      ConductSettingsFormSchema.safeParse({ ...valid, half_life_days: 3 })
        .success,
    ).toBe(false);
  });
});
