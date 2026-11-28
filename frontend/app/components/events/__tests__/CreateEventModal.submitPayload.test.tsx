// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { openTab, orgDefaults, submit, Wrapper } from './eventModalFixtures';

const api = vi.hoisted(() => ({
  getOrgEventDefaults: vi.fn(),
  createEvent: vi.fn(),
  createRepeater: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  fetchOrganization: vi.fn().mockResolvedValue({ pk: 1, staff_ids: [] }),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useCreateEventMutation: () => ({
    mutateAsync: api.createEvent,
    isPending: false,
  }),
  useCreateEventRepeaterMutation: () => ({
    mutateAsync: api.createRepeater,
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));
vi.mock('../form/sections/EventTournamentFields', () => ({
  EventTournamentFields: () => null,
}));
vi.mock('../form/fields/TimezoneField', () => ({ TimezoneField: () => null }));
vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: () => null,
}));
vi.mock('../DiscordRolePicker', () => ({ DiscordRolePicker: () => null }));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-25T12:00:00Z'));
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
  api.createEvent.mockResolvedValue({ id: 99 });
  api.createRepeater.mockResolvedValue({ id: 98 });
});

afterEach(() => {
  vi.useRealTimers();
});

async function renderReady() {
  render(<CreateEventModal open onOpenChange={() => {}} organizationId={1} />, {
    wrapper: Wrapper,
  });
  fireEvent.change(await screen.findByTestId('event-name-input'), {
    target: { value: 'Night 5' },
  });
}

describe('CreateEventModal submit payloads', () => {
  it('fills repeater defaults and merges lobby and draft settings', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    openTab(/lobby/i);
    fireEvent.pointerDown(await screen.findByTestId('lobby-password-mode'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    fireEvent.click(await screen.findByTestId('lobby-password-mode-fixed'));
    fireEvent.change(await screen.findByTestId('lobby-password-input'), {
      target: { value: 'secret12' },
    });
    openTab(/discord/i);
    fireEvent.click(
      await screen.findByTestId('discord-discord_notify_new_events'),
    );
    submit();
    await waitFor(() => expect(api.createRepeater).toHaveBeenCalled());
    expect(api.createRepeater.mock.calls[0][0]).toEqual(REPEATER_PAYLOAD);
    expect(api.createEvent).not.toHaveBeenCalled();
  });

  it.each([
    ['immediate', true],
    ['manual', false],
  ] as const)(
    'passes openSignups for signup_open_mode=%s',
    async (mode, openSignups) => {
      await renderReady();
      fireEvent.change(screen.getByTestId('event-scheduled-input'), {
        target: { value: '2026-12-04T18:00' },
      });
      fireEvent.click(screen.getByTestId(`signup-open-mode-${mode}`));
      submit();
      await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
      expect(api.createEvent.mock.calls[0][0].openSignups).toBe(openSignups);
    },
  );
});

const REPEATER_PAYLOAD = {
  allow_active_mmr: true,
  allow_battlecup_rating: true,
  allow_previous_rank: true,
  allow_spot_transfer: false,
  allow_user_signups: true,
  auto_confirm: false,
  captains_draft_time: 10,
  custom_game_name: '',
  day_of_week: null,
  description: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
  discord_announcement_role_ids: [],
  discord_confirm_attendance: false,
  discord_confirm_attendance_channel_id: '',
  discord_confirm_attendance_hours: 2,
  discord_create_event: false,
  discord_event_description: '',
  discord_event_info: '',
  discord_event_title: '',
  discord_mark_interested: false,
  discord_new_event_channel_id: '',
  discord_notify_new_events: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_profile_reminder: false,
  discord_profile_reminder_channel_id: '',
  discord_profile_reminder_hours: 24,
  discord_require_battlecup_screenshot: false,
  discord_require_rank_screenshot: false,
  discord_send_lobby_info: false,
  discord_signup_reminder: false,
  discord_signup_reminder_hours: 24,
  discord_signup_role_ids: [],
  discord_start_mention: false,
  discord_start_mention_minutes: 15,
  discord_start_mention_scope: 'all_active',
  discord_sync_signups: false,
  dota_lobby_launch: 'manual',
  dota_lobby_mode: 'off',
  dota_lobby_password: 'secret12',
  dota_lobby_password_mode: 'fixed',
  dota_lobby_region: '',
  draft_grace_time_ms: 30000,
  draft_reserve_time_ms: 30000,
  draft_timeout_action: 'skip_turn',
  draft_timer_enabled: true,
  draft_type: 'shuffle',
  ends_at: null,
  event_voice_channel_id: '',
  frequency: 'weekly',
  game_mode: 'normal',
  game_type: 1,
  generate_days_ahead: 7,
  hero_grace_time_ms: 30000,
  hero_reserve_time_ms: 90000,
  hero_timer_enabled: true,
  line_switch_restamps: true,
  line_withdraw_forfeits: true,
  lobby_steam_league_id: null,
  min_mmr: null,
  name: 'Night 5',
  number_of_teams: null,
  organization: 1,
  people_per_team: 5,
  post_cull_fill_mode: 'line_order',
  ready_check_chase_minutes: 30,
  ready_check_close_minutes: 10,
  ready_check_drop_notice: true,
  ready_check_escalation_minutes: 30,
  ready_check_low_completion_action: 'non_binding',
  ready_check_min_completion_pct: 70,
  ready_check_notify_on_signup: true,
  ready_check_open_minutes: 120,
  ready_check_scope: 'main_only',
  require_mmr_verified: false,
  require_profile_complete: false,
  require_steam_id: false,
  roll_call_enabled: false,
  roll_call_mode: 'manual',
  signup_open_mode: 'manual',
  signups_open_hours_before: 72,
  staff_reason_policy: 'optional',
  start_cull_enabled: false,
  start_cull_minutes_after: 1,
  starts_at: '2026-11-25',
  time_of_day: '19:00',
  timezone: 'America/New_York',
  tournament_league: null,
  tournament_name: 'Night Cup',
  tournament_type: 'double_elimination',
  voice_presence_confirms: false,
};
