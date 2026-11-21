import { describe, it, expect } from 'vitest'
import { eventSchema } from '~/components/events/schemas'

const baseEvent = (overrides = {}) => ({
  id: 1,
  organization: 1,
  organization_name: 'Org',
  name: 'Test Event',
  description: '',
  scheduled_at: '2026-12-01T20:00:00Z',
  signups_open_at: '2026-11-25T20:00:00Z',
  tournament: 1,
  created_by: 1,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  state: 'upcoming',
  game_type: 1,
  game_mode: 'normal',
  custom_game_name: '',
  captains_draft_time: 60,
  lobby_steam_league_id: 0,
  tournament_date: '2026-12-01T20:00:00Z',
  timezone: 'America/New_York',
  tournament_league: 1,
  tournament_name: '',
  tournament_type: 'single_elimination',
  draft_type: 'snake',
  people_per_team: 5,
  number_of_teams: null,
  min_players: 10,
  max_players: 20,
  signup_deadline_hours: 24,
  allow_team_signups: true,
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
  signup_count: 0,
  confirmed_count: 0,
  event_repeater: null,
  event_repeater_name: null,
  discord_create_event: false,
  discord_sync_signups: false,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_mark_interested: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
  discord_signup_reminder: false,
  discord_signup_reminder_hours: 24,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_notify_new_events: false,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
  user_can_manage: false,
  ...overrides,
})

describe('eventSchema — single-event signup_reminder rejection', () => {
  it('rejects discord_signup_reminder=true when event_repeater is null', () => {
    const bad = baseEvent({
      event_repeater: null,
      discord_signup_reminder: true,
    })
    expect(() => eventSchema.parse(bad)).toThrow(/signup reminder.*subscribers/i)
  })

  it('accepts discord_signup_reminder=false on single events', () => {
    const ok = baseEvent({
      event_repeater: null,
      discord_signup_reminder: false,
    })
    expect(() => eventSchema.parse(ok)).not.toThrow()
  })

  it('accepts discord_signup_reminder=true when event_repeater is set', () => {
    const ok = baseEvent({
      event_repeater: 42,
      event_repeater_name: 'Weekly Series',
      discord_signup_reminder: true,
    })
    expect(() => eventSchema.parse(ok)).not.toThrow()
  })
})
