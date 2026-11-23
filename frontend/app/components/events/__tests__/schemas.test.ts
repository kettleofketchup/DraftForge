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
  eventSchema,
  eventSignupSchema,
  localToUTC,
  READY_CHECK_CONFIG_DEFAULTS,
  refineEventEnd,
  SIGNUP_OPEN_DEFAULTS,
  utcToLocalInput,
} from '~/components/events/schemas';

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
