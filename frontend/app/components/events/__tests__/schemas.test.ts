import { describe, it, expect } from 'vitest'
import { discordConfigSchema } from '~/components/events/schemas'

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
