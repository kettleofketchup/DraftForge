import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import {
  Commitment,
  createEventInputSchema,
  createSeriesEventInputSchema,
  DISCORD_CONFIG_DEFAULTS,
  discordConfigSchema,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  editEventFormSchema,
  eventResponseSchema,
  eventSchema,
  eventSignupSchema,
  localToUTC,
  READY_CHECK_CONFIG_DEFAULTS,
  refineEventEnd,
  SIGNUP_LINE_DEFAULTS,
  SIGNUP_OPEN_DEFAULTS,
  signupLineSchema,
  STAFF_REASON_POLICIES,
  STAFF_REASON_POLICY_LABELS,
  utcToLocalInput,
} from '~/components/events/schemas';
import { signupLineFrom } from '~/components/events/signupLine';

// A complete discordConfigSchema payload that intentionally omits the
// dropped `discord_subscriber_dm` and `discord_subscriber_dm_hours`
// fields. After PR-0 loosens those fields to optional, this should parse.
const baseDiscordConfig = {
  discord_create_event: false,
  discord_sync_signups: false,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_signup_reminder: false,
  discord_signup_reminder_hours: 24,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_mark_interested: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
  discord_confirm_attendance_channel_id: '',
  discord_profile_reminder_channel_id: '',
  discord_new_event_channel_id: '',
  discord_announcement_role_ids: [],
  discord_signup_role_ids: [],
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: true,
  // Approval requirements added on main `b95a0b37` (the schema was updated
  // but this fixture wasn't — surfaced when vitest started running in CI).
  require_steam_id: false,
  require_mmr_verified: false,
  require_profile_complete: false,
  roll_call_enabled: false,
  allow_user_signups: true,
  line_withdraw_forfeits: true,
  line_switch_restamps: true,
  staff_reason_policy: 'optional',
  allow_spot_transfer: false,
};

describe('discord_subscriber_dm tolerance', () => {
  it('discordConfigSchema parses payload missing the dropped fields', () => {
    expect(() => discordConfigSchema.parse(baseDiscordConfig)).not.toThrow();
  });

  it('discordConfigSchema also parses payloads that still include the fields', () => {
    expect(() =>
      discordConfigSchema.parse({
        ...baseDiscordConfig,
        discord_subscriber_dm: true,
        discord_subscriber_dm_hours: 24,
      }),
    ).not.toThrow();
  });
});

describe('refineEventEnd', () => {
  const schema = z
    .object({ scheduled_at: z.string(), event_ends_at: z.string().optional() })
    .superRefine(refineEventEnd);

  it('rejects an end before the start', () => {
    const result = schema.safeParse({
      scheduled_at: '2026-11-14T20:00',
      event_ends_at: '2026-11-14T19:00',
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ['event_ends_at'],
      message: 'End must be after start',
    });
  });

  it('rejects an end equal to the start', () => {
    const result = schema.safeParse({
      scheduled_at: '2026-11-14T20:00',
      event_ends_at: '2026-11-14T20:00',
    });
    expect(result.success).toBe(false);
  });

  it('accepts an end after the start, across midnight', () => {
    expect(
      schema.safeParse({
        scheduled_at: '2026-11-14T23:00',
        event_ends_at: '2026-11-15T01:00',
      }).success,
    ).toBe(true);
  });

  it('accepts an empty or missing end', () => {
    expect(
      schema.safeParse({ scheduled_at: '2026-11-14T20:00', event_ends_at: '' })
        .success,
    ).toBe(true);
    expect(schema.safeParse({ scheduled_at: '2026-11-14T20:00' }).success).toBe(
      true,
    );
  });
});

describe('createSeriesEventInputSchema', () => {
  it('has no event_ends_at key', () => {
    expect(Object.keys(createSeriesEventInputSchema.shape)).not.toContain(
      'event_ends_at',
    );
  });

  it('parses a series one-off payload', () => {
    const result = createSeriesEventInputSchema.safeParse({
      name: 'One-off',
      description: '',
      scheduled_at: '2026-11-14T20:00',
      tournament_league: null,
      tournament_name: 'Cup',
      tournament_type: 'double_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      game_mode: 'normal',
      custom_game_name: '',
      captains_draft_time: 10,
      lobby_steam_league_id: null,
      people_per_team: 5,
      number_of_teams: null,
      timezone: 'America/New_York',
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
      ...SIGNUP_OPEN_DEFAULTS,
    });
    expect(result.success).toBe(true);
  });
});

describe('utcToLocalInput', () => {
  it('formats a UTC instant in the event timezone', () => {
    expect(utcToLocalInput('2026-11-15T01:00:00Z', 'America/New_York')).toBe(
      '2026-11-14T20:00',
    );
  });

  it('round-trips through localToUTC', () => {
    const local = utcToLocalInput('2026-11-15T01:00:00Z', 'America/New_York');
    expect(localToUTC(local, 'America/New_York')).toBe(
      '2026-11-15T01:00:00.000Z',
    );
  });

  it('returns an empty string for a missing value', () => {
    expect(utcToLocalInput(null, 'America/New_York')).toBe('');
  });
});

describe('eventSchema end and staff fields', () => {
  it('declares ends_at, host, helpers, contributions_awarded_at and user_can_manage_event_staff', () => {
    expect(Object.keys(eventSchema.shape)).toEqual(
      expect.arrayContaining([
        'ends_at',
        'host',
        'helpers',
        'contributions_awarded_at',
        'user_can_manage_event_staff',
      ]),
    );
  });
});

describe('per-post channel fields', () => {
  const POST_CHANNEL_KEYS = [
    'discord_confirm_attendance_channel_id',
    'discord_profile_reminder_channel_id',
    'discord_new_event_channel_id',
  ] as const;
  const pick = { discord_announcement_channel_id: true } as const;

  it('parses an event payload without the post channel fields as blank', () => {
    const response = eventResponseSchema
      .pick({
        ...pick,
        discord_confirm_attendance_channel_id: true,
        discord_profile_reminder_channel_id: true,
        discord_new_event_channel_id: true,
      })
      .parse({ discord_announcement_channel_id: '123' });
    const event = z
      .object({
        discord_announcement_channel_id:
          eventSchema.shape.discord_announcement_channel_id,
        discord_confirm_attendance_channel_id:
          eventSchema.shape.discord_confirm_attendance_channel_id,
        discord_profile_reminder_channel_id:
          eventSchema.shape.discord_profile_reminder_channel_id,
        discord_new_event_channel_id:
          eventSchema.shape.discord_new_event_channel_id,
      })
      .parse({ discord_announcement_channel_id: '123' });
    for (const key of POST_CHANNEL_KEYS) {
      expect(response[key]).toBe('');
      expect(event[key]).toBe('');
    }
  });

  it('keeps a stored post channel id', () => {
    const parsed = eventResponseSchema
      .pick({ discord_new_event_channel_id: true })
      .parse({ discord_new_event_channel_id: '987654321098765432' });
    expect(parsed.discord_new_event_channel_id).toBe('987654321098765432');
  });

  it('defaults every post channel to blank', () => {
    for (const key of POST_CHANNEL_KEYS) {
      expect(DISCORD_CONFIG_DEFAULTS[key]).toBe('');
    }
  });
});

describe('eventSchema leadership viewer flags', () => {
  const flags = z.object({
    can_review_captains: eventSchema.shape.can_review_captains,
    pending_captain_reviews: eventSchema.shape.pending_captain_reviews,
  });

  it('parses the leadership viewer flags when present and tolerates their absence', () => {
    const present = flags.parse({
      can_review_captains: true,
      pending_captain_reviews: 2,
    });
    expect(present.pending_captain_reviews).toBe(2);
    expect(present.can_review_captains).toBe(true);
    const absent = flags.parse({});
    expect(absent.pending_captain_reviews).toBeUndefined();
    expect(absent.can_review_captains).toBeUndefined();
  });
});

// Pre-refactor key lists: the fragment composition must keep them exact.
const TEMPLATE_KEYS = [
  'name',
  'description',
  'tournament_name',
  'tournament_type',
  'game_type',
  'draft_type',
  'game_mode',
  'custom_game_name',
  'captains_draft_time',
  'lobby_steam_league_id',
  'people_per_team',
  'number_of_teams',
  'timezone',
];
const DISCORD_KEYS = [
  'discord_create_event',
  'discord_sync_signups',
  'discord_event_title',
  'discord_event_description',
  'discord_event_info',
  'discord_signup_reminder',
  'discord_signup_reminder_hours',
  'discord_confirm_attendance',
  'discord_confirm_attendance_hours',
  'discord_profile_reminder',
  'discord_profile_reminder_hours',
  'discord_mark_interested',
  'discord_post_signups',
  'discord_post_signups_channel_id',
  'discord_announcement',
  'discord_announcement_channel_id',
  'discord_announcement_hours',
  'discord_confirm_attendance_channel_id',
  'discord_profile_reminder_channel_id',
  'discord_new_event_channel_id',
  'discord_announcement_role_ids',
  'discord_signup_role_ids',
  'discord_start_mention',
  'discord_start_mention_minutes',
  'discord_start_mention_scope',
  'discord_subscriber_dm',
  'discord_subscriber_dm_hours',
  'discord_require_rank_screenshot',
  'discord_require_battlecup_screenshot',
  'min_mmr',
  'allow_active_mmr',
  'allow_previous_rank',
  'allow_battlecup_rating',
  'require_steam_id',
  'require_mmr_verified',
  'require_profile_complete',
  'allow_user_signups',
  'line_withdraw_forfeits',
  'line_switch_restamps',
  'staff_reason_policy',
  'allow_spot_transfer',
];
const SIGNUP_OPEN_KEYS = ['signup_open_mode', 'signups_open_hours_before'];
const LOBBY_KEYS = [
  'dota_lobby_mode',
  'dota_lobby_launch',
  'dota_lobby_region',
  'discord_send_lobby_info',
  'dota_lobby_password_mode',
  'dota_lobby_password',
  'dota_lobby_password_saved',
];
const READY_CHECK_KEYS = Object.keys(READY_CHECK_CONFIG_DEFAULTS);

describe('event form schema key sets', () => {
  const keys = (shape: object) => Object.keys(shape).sort();

  it('createEventInputSchema', () => {
    expect(keys(createEventInputSchema.shape)).toEqual(
      [
        ...TEMPLATE_KEYS,
        ...DISCORD_KEYS,
        ...LOBBY_KEYS,
        ...READY_CHECK_KEYS,
        ...SIGNUP_OPEN_KEYS,
        ...[
          'scheduled_at',
          'organization',
          'tournament_league',
          'discord_notify_new_events',
          'is_recurring',
          'frequency',
          'day_of_week',
          'time_of_day',
          'starts_at',
          'ends_at',
          'generate_days_ahead',
          'event_ends_at',
        ],
      ].sort(),
    );
  });

  it('createSeriesEventInputSchema', () => {
    expect(keys(createSeriesEventInputSchema.shape)).toEqual(
      [
        ...TEMPLATE_KEYS,
        ...DISCORD_KEYS,
        ...LOBBY_KEYS,
        ...READY_CHECK_KEYS,
        ...SIGNUP_OPEN_KEYS,
        ...['scheduled_at', 'tournament_league'],
      ].sort(),
    );
  });

  it('editEventFormSchema', () => {
    expect(keys(editEventFormSchema.shape)).toEqual(
      [
        ...TEMPLATE_KEYS,
        ...DISCORD_KEYS,
        ...LOBBY_KEYS,
        ...READY_CHECK_KEYS,
        ...SIGNUP_OPEN_KEYS,
        ...[
          'scheduled_at',
          'event_ends_at',
          'tournament_league',
          'draft_timer_enabled',
          'draft_grace_time_s',
          'draft_reserve_time_s',
          'draft_timeout_action',
          'hero_timer_enabled',
          'hero_grace_time_s',
          'hero_reserve_time_s',
        ],
      ].sort(),
    );
  });
});

describe('eventSignupSchema line fields', () => {
  const oldPayload = {
    id: 1,
    event: 2,
    user: 3,
    username: 'player',
    user_avatar: null,
    user_data: null,
    dota_profile: null,
    org_user_mmr: null,
    org_user_pk: null,
    organization: null,
    suggested_mmr: 3000,
    suggested_mmr_range: [2500, 3500],
    suggested_mmr_range_source: 'fallback',
    event_team: null,
    signup_type: 'player',
    status: 'rsvp',
    waitlist_position: null,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
  };

  it('fills defaults for a payload without line fields', () => {
    const parsed = eventSignupSchema.parse(oldPayload);
    expect(parsed.signed_up_at).toBeNull();
    expect(parsed.commitment).toBe('main');
    expect(parsed.rsvp_class).toBe('standard');
    expect(parsed.first_signed_up_at).toBeNull();
    expect(parsed.line_rank).toBeNull();
  });

  it('round-trips line fields', () => {
    const lineFields = {
      signed_up_at: '2026-11-02T12:00:00Z',
      commitment: Commitment.MAYBE,
      rsvp_class: 'standard',
      first_signed_up_at: '2026-10-30T08:00:00Z',
      line_rank: 4,
    };
    const parsed = eventSignupSchema.parse({ ...oldPayload, ...lineFields });
    expect(parsed).toMatchObject(lineFields);
  });

  it('rejects a non-integer line_rank', () => {
    expect(
      eventSignupSchema.safeParse({ ...oldPayload, line_rank: 1.5 }).success,
    ).toBe(false);
  });

  it('rejects an unknown commitment', () => {
    expect(
      eventSignupSchema.safeParse({ ...oldPayload, commitment: 'sometimes' })
        .success,
    ).toBe(false);
  });

  it('exposes the Commitment values', () => {
    expect(Commitment).toEqual({ MAIN: 'main', MAYBE: 'maybe' });
  });

  it('parses a signup with no MMR suggestion', () => {
    const parsed = eventSignupSchema.parse({
      ...oldPayload,
      suggested_mmr: null,
      suggested_mmr_range: null,
      suggested_mmr_range_source: 'none',
    });
    expect(parsed.suggested_mmr).toBeNull();
    expect(parsed.suggested_mmr_range).toBeNull();
    expect(parsed.suggested_mmr_range_source).toBe('none');
  });
});

describe('eventSchema user_is_event_operator', () => {
  const payload = {
    ...baseDiscordConfig,
    id: 1,
    organization: 1,
    organization_name: 'Org',
    event_repeater: null,
    event_repeater_name: null,
    name: 'Event',
    description: '',
    scheduled_at: '2026-12-01T20:00:00Z',
    signups_open_at: null,
    state: 'upcoming',
    tournament: null,
    created_by: 1,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    signup_count: 0,
    confirmed_count: 0,
    tournament_name: '',
    tournament_league: null,
    tournament_type: 'single_elimination',
    game_type: 1,
    draft_type: 'snake',
    game_mode: 'normal',
    custom_game_name: '',
    captains_draft_time: 60,
    lobby_steam_league_id: null,
    people_per_team: 5,
    number_of_teams: null,
    tournament_date: null,
    timezone: 'UTC',
    min_players: null,
    max_players: null,
    signup_deadline_hours: null,
    allow_team_signups: false,
    auto_approve: false,
    auto_confirm: false,
    roll_call_mode: 'manual',
  };

  it('defaults to false when the key is missing', () => {
    expect(eventSchema.parse(payload).user_is_event_operator).toBe(false);
  });

  it('parses true', () => {
    expect(
      eventSchema.parse({ ...payload, user_is_event_operator: true })
        .user_is_event_operator,
    ).toBe(true);
  });
});

describe('signup line rules', () => {
  it('defaults both rules on', () => {
    expect(SIGNUP_LINE_DEFAULTS).toEqual({
      line_withdraw_forfeits: true,
      line_switch_restamps: true,
      staff_reason_policy: 'optional',
      allow_spot_transfer: false,
    });
    expect(DISCORD_CONFIG_DEFAULTS).toMatchObject(SIGNUP_LINE_DEFAULTS);
  });

  it('rejects a non-boolean rule', () => {
    expect(
      signupLineSchema.safeParse({
        line_withdraw_forfeits: 'yes',
        line_switch_restamps: true,
        staff_reason_policy: 'optional',
        allow_spot_transfer: false,
      }).success,
    ).toBe(false);
    expect(
      discordConfigSchema.safeParse({
        ...baseDiscordConfig,
        line_switch_restamps: 1,
      }).success,
    ).toBe(false);
  });

  it('tolerates event payloads without the rules', () => {
    const rules = z.object({
      line_withdraw_forfeits: eventSchema.shape.line_withdraw_forfeits,
      line_switch_restamps: eventResponseSchema.shape.line_switch_restamps,
    });
    expect(rules.parse({})).toEqual({});
    expect(
      rules.parse({
        line_withdraw_forfeits: false,
        line_switch_restamps: false,
      }),
    ).toEqual({ line_withdraw_forfeits: false, line_switch_restamps: false });
  });

  it('signupLineFrom falls back to the defaults', () => {
    expect(signupLineFrom({})).toEqual(SIGNUP_LINE_DEFAULTS);
    expect(signupLineFrom(null)).toEqual(SIGNUP_LINE_DEFAULTS);
    expect(signupLineFrom(undefined)).toEqual(SIGNUP_LINE_DEFAULTS);
  });

  it('signupLineFrom copies loaded values', () => {
    expect(
      signupLineFrom({
        line_withdraw_forfeits: false,
        line_switch_restamps: true,
        staff_reason_policy: 'placements',
        allow_spot_transfer: true,
      }),
    ).toEqual({
      line_withdraw_forfeits: false,
      line_switch_restamps: true,
      staff_reason_policy: 'placements',
      allow_spot_transfer: true,
    });
  });

  it('signupLineFrom defaults spot transfer off', () => {
    expect(signupLineFrom({}).allow_spot_transfer).toBe(false);
    expect(
      signupLineFrom({ allow_spot_transfer: true }).allow_spot_transfer,
    ).toBe(true);
  });

  it('rejects a non-boolean spot transfer setting', () => {
    expect(
      signupLineSchema.safeParse({
        ...SIGNUP_LINE_DEFAULTS,
        allow_spot_transfer: 'yes',
      }).success,
    ).toBe(false);
  });

  it('tolerates event payloads without the spot transfer setting', () => {
    expect(eventSchema.shape.allow_spot_transfer.parse(undefined)).toBe(
      undefined,
    );
    expect(eventResponseSchema.shape.allow_spot_transfer.parse(true)).toBe(
      true,
    );
  });

  it('signupLineFrom defaults a missing staff reason policy to optional', () => {
    expect(
      signupLineFrom({
        line_withdraw_forfeits: false,
        line_switch_restamps: false,
      }).staff_reason_policy,
    ).toBe('optional');
  });

  it('rejects an unknown staff reason policy', () => {
    expect(
      signupLineSchema.safeParse({
        ...SIGNUP_LINE_DEFAULTS,
        staff_reason_policy: 'sometimes',
      }).success,
    ).toBe(false);
    expect(
      eventResponseSchema.shape.staff_reason_policy.safeParse('sometimes')
        .success,
    ).toBe(false);
  });

  it('tolerates event payloads without the staff reason policy', () => {
    expect(eventSchema.shape.staff_reason_policy.parse(undefined)).toBe(
      undefined,
    );
    expect(
      eventResponseSchema.shape.staff_reason_policy.parse('all_staff_changes'),
    ).toBe('all_staff_changes');
  });

  it('labels every staff reason policy', () => {
    expect(STAFF_REASON_POLICY_LABELS).toEqual({
      optional: 'Optional',
      placements: 'Required for placements',
      all_staff_changes: 'Required for every staff change',
    });
    expect(Object.keys(STAFF_REASON_POLICY_LABELS)).toEqual([
      ...STAFF_REASON_POLICIES,
    ]);
  });
});
