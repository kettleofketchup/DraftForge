import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getEvent, getEvents } from '../eventsAPI';

const staffUser = {
  pk: 7,
  username: 'hostuser',
  nickname: null,
  discordNickname: 'Host',
  guildNickname: null,
  avatarUrl: 'https://cdn.discordapp.com/avatars/7/abc.png',
};

const listItem = {
  id: 12,
  organization: 3,
  organization_name: 'Test Org',
  name: 'Friday Inhouse',
  scheduled_at: '2026-11-27T01:00:00Z',
  ends_at: null,
  state: 'signups_open',
  game_type: 1,
  tournament_name: '',
  tournament_league: null,
  tournament_type: 'double_elimination',
  draft_type: 'snake',
  people_per_team: 5,
  number_of_teams: 2,
  signup_count: 9,
  confirmed_count: 4,
  event_repeater: 2,
  is_off_schedule: false,
  discord_announcement: true,
  discord_announcement_hours: 24,
  discord_announcement_channel_id: '1234567890',
  discord_signup_reminder: true,
  discord_signup_reminder_hours: 48,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_start_mention: false,
  discord_start_mention_minutes: 15,
  ready_check_scope: 'main_only',
  ready_check_open_minutes: 30,
  ready_check_escalation_minutes: 15,
  ready_check_close_minutes: 5,
  ready_check_chase_minutes: null,
  ready_check_min_completion_pct: 50,
  ready_check_low_completion_action: 'non_binding',
  ready_check_notify_on_signup: true,
  ready_check_drop_notice: true,
  start_cull_enabled: false,
  start_cull_minutes_after: 10,
  post_cull_fill_mode: 'line_order',
  event_voice_channel_id: '',
  voice_presence_confirms: false,
  user_can_manage: true,
  user_can_manage_event_staff: false,
  manage_viewer_pk: 7,
};

const detail = {
  ...listItem,
  user_can_manage: false,
  user_can_manage_event_staff: false,
  event_repeater_name: 'Weekly Inhouse',
  description: '<p>Bring snacks</p>',
  signups_open_at: '2026-11-24T01:00:00Z',
  host: staffUser,
  helpers: [{ ...staffUser, pk: 8, username: 'helper' }],
  contributions_awarded_at: null,
  conduct_finalized_at: null,
  tournament: null,
  created_by: 7,
  created_at: '2026-11-20T10:00:00.123456Z',
  updated_at: '2026-11-21T10:00:00.123456Z',
  tournament_date: null,
  game_mode: 'captains_mode',
  custom_game_name: '',
  captains_draft_time: 10,
  lobby_steam_league_id: null,
  draft_timer_enabled: true,
  draft_grace_time_ms: 30000,
  draft_reserve_time_ms: 30000,
  draft_timeout_action: 'skip_turn',
  hero_timer_enabled: true,
  hero_grace_time_ms: 30000,
  hero_reserve_time_ms: 90000,
  timezone: 'America/New_York',
  min_players: null,
  max_players: 10,
  signup_deadline_hours: null,
  allow_team_signups: false,
  allow_user_signups: true,
  auto_approve: false,
  auto_confirm: false,
  require_mmr_verified: false,
  require_steam_id: true,
  require_profile_complete: false,
  roll_call_enabled: true,
  roll_call_mode: 'manual',
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: false,
  signup_open_mode: 'scheduled',
  signups_open_hours_before: 72,
  discord_create_event: true,
  discord_sync_signups: true,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_mark_interested: true,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement_role_ids: ['555'],
  discord_signup_role_ids: [],
  discord_start_mention_scope: 'all_active',
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
  auto_create_hero_drafts: false,
  discord_send_draft_link: true,
  discord_send_herodraft_link: true,
  dota_lobby_mode: 'off',
  dota_lobby_launch: 'manual',
  dota_lobby_region: '',
  discord_send_lobby_info: false,
  dota_lobby_password_mode: 'random',
  can_review_captains: true,
  pending_captain_reviews: 2,
};

beforeEach(() => {
  get.mockReset();
});

describe('getEvents', () => {
  it('parses the slim list payload', async () => {
    get.mockResolvedValue({ data: [listItem] });
    await expect(getEvents({ organization: 3 })).resolves.toEqual([listItem]);
    expect(get).toHaveBeenCalledWith('/events/?organization=3');
  });

  it('parses an anonymous list item without the viewer flags', async () => {
    const {
      user_can_manage: _m,
      user_can_manage_event_staff: _s,
      ...anon
    } = listItem;
    get.mockResolvedValue({ data: [anon] });
    await expect(getEvents()).resolves.toEqual([anon]);
  });

  it('rejects a list item that drifted from the serializer', async () => {
    get.mockResolvedValue({ data: [{ ...listItem, signup_count: '9' }] });
    await expect(getEvents()).rejects.toBeInstanceOf(ZodError);
  });

  it('rejects a body that is not a list', async () => {
    get.mockResolvedValue({ data: { results: [listItem] } });
    await expect(getEvents()).rejects.toBeInstanceOf(ZodError);
  });
});

describe('getEvent', () => {
  it('parses the detail payload', async () => {
    get.mockResolvedValue({ data: detail });
    await expect(getEvent(12)).resolves.toEqual(detail);
    expect(get).toHaveBeenCalledWith('/events/12/');
  });

  it('accepts a single event whose stored signup reminder is still on', async () => {
    const single = {
      ...detail,
      event_repeater: null,
      event_repeater_name: null,
      discord_signup_reminder: true,
    };
    get.mockResolvedValue({ data: single });
    await expect(getEvent(12)).resolves.toEqual(single);
  });

  it('rejects a detail payload with an unknown state', async () => {
    get.mockResolvedValue({ data: { ...detail, state: 'archived' } });
    await expect(getEvent(12)).rejects.toBeInstanceOf(ZodError);
  });

  it('rejects a detail payload missing a serializer field', async () => {
    const { helpers: _h, ...missing } = detail;
    get.mockResolvedValue({ data: missing });
    await expect(getEvent(12)).rejects.toBeInstanceOf(ZodError);
  });
});
