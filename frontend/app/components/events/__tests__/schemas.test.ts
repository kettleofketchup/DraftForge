import { describe, it, expect } from 'vitest'
import { z } from 'zod'
import {
  createSeriesEventInputSchema,
  discordConfigSchema,
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  eventSchema,
  localToUTC,
  refineEventEnd,
  utcToLocalInput,
} from '~/components/events/schemas'

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
  // but this fixture wasn't — surfaced when T1 wired vitest into CI).
  require_steam_id: false,
  require_mmr_verified: false,
  require_profile_complete: false,
}

describe('discord_subscriber_dm tolerance', () => {
  it('discordConfigSchema parses payload missing the dropped fields', () => {
    expect(() => discordConfigSchema.parse(baseDiscordConfig)).not.toThrow()
  })

  it('discordConfigSchema also parses payloads that still include the fields', () => {
    expect(() => discordConfigSchema.parse({
      ...baseDiscordConfig,
      discord_subscriber_dm: true,
      discord_subscriber_dm_hours: 24,
    })).not.toThrow()
  })
})

describe('refineEventEnd', () => {
  const schema = z
    .object({ scheduled_at: z.string(), event_ends_at: z.string().optional() })
    .superRefine(refineEventEnd)

  it('rejects an end before the start', () => {
    const result = schema.safeParse({ scheduled_at: '2026-11-14T20:00', event_ends_at: '2026-11-14T19:00' })
    expect(result.success).toBe(false)
    expect(result.error?.issues[0]).toMatchObject({
      path: ['event_ends_at'],
      message: 'End must be after start',
    })
  })

  it('rejects an end equal to the start', () => {
    const result = schema.safeParse({ scheduled_at: '2026-11-14T20:00', event_ends_at: '2026-11-14T20:00' })
    expect(result.success).toBe(false)
  })

  it('accepts an end after the start, across midnight', () => {
    expect(schema.safeParse({ scheduled_at: '2026-11-14T23:00', event_ends_at: '2026-11-15T01:00' }).success).toBe(true)
  })

  it('accepts an empty or missing end', () => {
    expect(schema.safeParse({ scheduled_at: '2026-11-14T20:00', event_ends_at: '' }).success).toBe(true)
    expect(schema.safeParse({ scheduled_at: '2026-11-14T20:00' }).success).toBe(true)
  })
})

describe('createSeriesEventInputSchema', () => {
  it('has no event_ends_at key', () => {
    expect(Object.keys(createSeriesEventInputSchema.shape)).not.toContain('event_ends_at')
  })

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
    })
    expect(result.success).toBe(true)
  })
})

describe('utcToLocalInput', () => {
  it('formats a UTC instant in the event timezone', () => {
    expect(utcToLocalInput('2026-11-15T01:00:00Z', 'America/New_York')).toBe('2026-11-14T20:00')
  })

  it('round-trips through localToUTC', () => {
    const local = utcToLocalInput('2026-11-15T01:00:00Z', 'America/New_York')
    expect(localToUTC(local, 'America/New_York')).toBe('2026-11-15T01:00:00.000Z')
  })

  it('returns an empty string for a missing value', () => {
    expect(utcToLocalInput(null, 'America/New_York')).toBe('')
  })
})

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
    )
  })
})
