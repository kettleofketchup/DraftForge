import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { readyCheckResetValues } from '~/components/events/form/defaults';
import {
  eventSchema,
  LOW_COMPLETION_ACTION_LABELS,
  POST_CULL_FILL_MODE_LABELS,
  READY_CHECK_CONFIG_DEFAULTS,
  READY_CHECK_PREFILL_KEYS,
  READY_CHECK_PRESET_ON,
  READY_CHECK_SCOPE_LABELS,
  readyCheckConfigSchema,
  refineReadyCheck,
  REMOVED_SIGNUP_STATUSES,
  ROLL_CALL_MODE_LABELS,
  SignupStatus,
  type ReadyCheckFields,
} from '~/components/events/schemas';

const AUTO_CONFIRM_MESSAGE =
  'Auto-confirm must be off while the ready check (roll call) is on: every member has to confirm themselves.';
const CLOSE_MESSAGE =
  'The check must close after it opens (close minutes must be fewer than open minutes).';
const ESCALATION_MESSAGE =
  'Escalation must fall between open and close, or be 0 to turn it off.';
const CHASE_MESSAGE =
  'The chase falls before the check opens: chase + close must be less than open.';

type RefineOpts = Parameters<typeof refineReadyCheck>[2];

function issues(
  overrides: Partial<ReadyCheckFields>,
  opts?: RefineOpts,
): { path: PropertyKey[]; message: string }[] {
  const schema = readyCheckConfigSchema.superRefine((v, ctx) =>
    refineReadyCheck(v, ctx, opts),
  );
  const result = schema.safeParse({
    ...READY_CHECK_CONFIG_DEFAULTS,
    ...overrides,
  });
  if (result.success) return [];
  return result.error.issues.map((i) => ({
    path: i.path,
    message: i.message,
  }));
}

describe('readyCheckConfigSchema defaults', () => {
  it('parses an empty object to the defaults', () => {
    expect(readyCheckConfigSchema.parse({})).toEqual(
      READY_CHECK_CONFIG_DEFAULTS,
    );
  });

  it('defaults to today behaviour', () => {
    expect(READY_CHECK_CONFIG_DEFAULTS).toEqual({
      roll_call_enabled: false,
      roll_call_mode: 'manual',
      auto_confirm: false,
      ready_check_scope: 'main_only',
      ready_check_open_minutes: 120,
      ready_check_escalation_minutes: 30,
      ready_check_close_minutes: 10,
      ready_check_chase_minutes: 30,
      ready_check_min_completion_pct: 70,
      ready_check_low_completion_action: 'non_binding',
      ready_check_notify_on_signup: true,
      ready_check_drop_notice: true,
      start_cull_enabled: false,
      start_cull_minutes_after: 1,
      post_cull_fill_mode: 'line_order',
      event_voice_channel_id: '',
      voice_presence_confirms: false,
    });
  });

  it('has a preset that turns the check on in automatic mode', () => {
    expect(READY_CHECK_PRESET_ON).toEqual({
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
      auto_confirm: false,
    });
  });

  it('prefills every key but auto_confirm', () => {
    expect(READY_CHECK_PREFILL_KEYS).not.toContain('auto_confirm');
    expect([...READY_CHECK_PREFILL_KEYS].sort()).toEqual(
      Object.keys(READY_CHECK_CONFIG_DEFAULTS)
        .filter((k) => k !== 'auto_confirm')
        .sort(),
    );
  });

  it('exposes labels and the removed statuses', () => {
    expect(SignupStatus.DROPPED).toBe('dropped');
    expect(REMOVED_SIGNUP_STATUSES).toEqual([
      'cancelled',
      'rejected',
      'dropped',
    ]);
    expect(ROLL_CALL_MODE_LABELS).toEqual({
      manual: 'Staff-verified',
      automatic: 'Automatic',
    });
    expect(READY_CHECK_SCOPE_LABELS.main_and_fill).toBe(
      'Main roster and fill list',
    );
    expect(LOW_COMPLETION_ACTION_LABELS.non_binding).toBe(
      'Make the check non-binding (drop nobody)',
    );
    expect(POST_CULL_FILL_MODE_LABELS.voice_arrival).toBe(
      'Order of arrival in the event call',
    );
  });
});

describe('readyCheckConfigSchema bounds', () => {
  it('accepts chase null and escalation 0', () => {
    expect(issues({ ready_check_chase_minutes: null })).toEqual([]);
    expect(issues({ ready_check_escalation_minutes: 0 })).toEqual([]);
  });

  it('rejects chase 0 and pct 101', () => {
    expect(issues({ ready_check_chase_minutes: 0 })).not.toEqual([]);
    expect(issues({ ready_check_min_completion_pct: 101 })).not.toEqual([]);
  });

  it('rejects a non-snowflake voice channel id', () => {
    expect(issues({ event_voice_channel_id: 'abc' })).not.toEqual([]);
    expect(issues({ event_voice_channel_id: '123456789012345678' })).toEqual(
      [],
    );
  });
});

describe('refineReadyCheck rules', () => {
  it('R1 lands on roll_call_enabled by default', () => {
    expect(issues({ roll_call_enabled: true, auto_confirm: true })).toEqual([
      { path: ['roll_call_enabled'], message: AUTO_CONFIRM_MESSAGE },
    ]);
  });

  it('R1 lands on auto_confirm when it is visible', () => {
    expect(
      issues(
        { roll_call_enabled: true, auto_confirm: true },
        { autoConfirmVisible: true },
      ),
    ).toEqual([{ path: ['auto_confirm'], message: AUTO_CONFIRM_MESSAGE }]);
  });

  it('R2 close must be before open', () => {
    expect(
      issues({
        ready_check_open_minutes: 10,
        ready_check_close_minutes: 10,
        ready_check_escalation_minutes: 0,
        ready_check_chase_minutes: null,
      }),
    ).toEqual([
      { path: ['ready_check_close_minutes'], message: CLOSE_MESSAGE },
    ]);
  });

  it('R3 escalation between open and close', () => {
    expect(issues({ ready_check_escalation_minutes: 200 })).toEqual([
      {
        path: ['ready_check_escalation_minutes'],
        message: ESCALATION_MESSAGE,
      },
    ]);
    expect(issues({ ready_check_escalation_minutes: 5 })).toEqual([
      {
        path: ['ready_check_escalation_minutes'],
        message: ESCALATION_MESSAGE,
      },
    ]);
  });

  it('R4 chase + close below open', () => {
    expect(issues({ ready_check_chase_minutes: 110 })).toEqual([
      { path: ['ready_check_chase_minutes'], message: CHASE_MESSAGE },
    ]);
  });

  it('R6 voice features need a channel, first trigger wins', () => {
    expect(
      issues({ start_cull_enabled: true, voice_presence_confirms: true }),
    ).toEqual([
      {
        path: ['start_cull_enabled'],
        message: 'The start cull needs an event voice channel.',
      },
    ]);
    expect(issues({ voice_presence_confirms: true })).toEqual([
      {
        path: ['voice_presence_confirms'],
        message: 'Voice presence confirms need an event voice channel.',
      },
    ]);
    expect(issues({ post_cull_fill_mode: 'voice_arrival' })).toEqual([
      {
        path: ['post_cull_fill_mode'],
        message: 'Filling by voice arrival needs an event voice channel.',
      },
    ]);
    expect(
      issues({
        start_cull_enabled: true,
        event_voice_channel_id: '123456789012345678',
      }),
    ).toEqual([]);
  });

  it('skips untouched groups when a baseline is given', () => {
    const legacy: Partial<ReadyCheckFields> = {
      roll_call_enabled: true,
      auto_confirm: true,
      ready_check_open_minutes: 10,
      ready_check_close_minutes: 10,
    };
    expect(issues(legacy, { baseline: legacy })).toEqual([]);
    expect(
      issues(
        { ...legacy, ready_check_close_minutes: 20 },
        { baseline: legacy },
      ).map((i) => i.path),
    ).toEqual([['ready_check_close_minutes']]);
  });

  it('treats keys missing from the baseline as defaults', () => {
    expect(issues({}, { baseline: {} })).toEqual([]);
    expect(
      issues({ voice_presence_confirms: true }, { baseline: {} }).map(
        (i) => i.path,
      ),
    ).toEqual([['voice_presence_confirms']]);
  });
});

describe('module load and eventSchema', () => {
  it('imports schemas without throwing', async () => {
    await expect(import('../schemas')).resolves.toBeDefined();
  });

  const baseEvent = {
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
    allow_user_signups: true,
    auto_approve: false,
    auto_confirm: false,
    require_mmr_verified: false,
    require_steam_id: false,
    require_profile_complete: false,
    roll_call_enabled: false,
    roll_call_mode: 'manual',
    allow_active_mmr: true,
    allow_previous_rank: true,
    allow_battlecup_rating: true,
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
    discord_require_rank_screenshot: false,
    discord_require_previous_rank_screenshot: false,
    discord_require_battlecup_screenshot: false,
    min_mmr: null,
  };

  it('accepts a payload without the ready check fields', () => {
    expect(() => eventSchema.parse(baseEvent)).not.toThrow();
  });

  it('carries the ready check fields through', () => {
    const parsed = eventSchema.parse({
      ...baseEvent,
      ready_check_chase_minutes: null,
      event_voice_channel_id: '123456789012345678',
    });
    expect(parsed.ready_check_chase_minutes).toBeNull();
    expect(parsed.event_voice_channel_id).toBe('123456789012345678');
  });

  it('rejects roll_call_mode none', () => {
    expect(() =>
      eventSchema.parse({ ...baseEvent, roll_call_mode: 'none' }),
    ).toThrow();
  });
});

describe('readyCheckResetValues', () => {
  it('keeps a null chase', () => {
    const values = readyCheckResetValues({
      ready_check_chase_minutes: null,
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
    });
    expect(values.ready_check_chase_minutes).toBeNull();
    expect(values.roll_call_enabled).toBe(true);
    expect(values.roll_call_mode).toBe('automatic');
    expect(values.ready_check_open_minutes).toBe(120);
  });

  it('returns the defaults for no source', () => {
    expect(readyCheckResetValues(undefined)).toEqual(
      READY_CHECK_CONFIG_DEFAULTS,
    );
    expect(readyCheckResetValues(null)).toEqual(READY_CHECK_CONFIG_DEFAULTS);
  });

  it('names every schema key', () => {
    expect(Object.keys(readyCheckResetValues({})).sort()).toEqual(
      Object.keys(readyCheckConfigSchema.shape).sort(),
    );
  });

  it('copies stored values', () => {
    const src = {
      ...READY_CHECK_CONFIG_DEFAULTS,
      ready_check_open_minutes: 300,
      event_voice_channel_id: '123456789012345678',
    };
    expect(readyCheckResetValues(src)).toEqual(src);
  });

  it('is z-compatible', () => {
    expect(
      z
        .object(readyCheckConfigSchema.shape)
        .safeParse(readyCheckResetValues(undefined)).success,
    ).toBe(true);
  });
});
