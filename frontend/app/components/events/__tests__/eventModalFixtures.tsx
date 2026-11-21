import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import type {
  EventRepeaterType,
  OrgEventDefaultsType,
} from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { READY_CHECK_CONFIG_DEFAULTS, type EventType } from '../schemas';

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

export function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={createI18nInstance('en')}>
        <TooltipProvider>{children}</TooltipProvider>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

export const config = {
  ...READY_CHECK_CONFIG_DEFAULTS,
  organization: 1,
  tournament_name: 'Night Cup',
  tournament_league: null,
  tournament_type: 'double_elimination',
  game_type: 1,
  draft_type: 'shuffle',
  game_mode: 'normal',
  custom_game_name: '',
  captains_draft_time: 10,
  lobby_steam_league_id: null,
  people_per_team: 5,
  number_of_teams: null,
  tournament_date: null,
  timezone: 'America/New_York',
  min_players: null,
  max_players: 20,
  signup_deadline_hours: null,
  allow_team_signups: false,
  allow_user_signups: true,
  auto_approve: true,
  auto_confirm: false,
  require_mmr_verified: false,
  require_steam_id: false,
  require_profile_complete: false,
  roll_call_enabled: false,
  roll_call_mode: 'manual' as const,
  signup_open_mode: 'manual' as const,
  signups_open_hours_before: 72,
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
  discord_announcement_role_ids: [] as string[],
  discord_signup_role_ids: [] as string[],
  discord_start_mention: false,
  discord_start_mention_minutes: 15,
  discord_start_mention_scope: 'all_active' as const,
  discord_require_rank_screenshot: false,
  discord_require_previous_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
};

export const orgDefaults = {
  id: 3,
  ...config,
} satisfies OrgEventDefaultsType;

export const repeater = {
  ...config,
  id: 7,
  organization_name: 'Org',
  name: 'Sunday Turbo',
  description: '',
  frequency: 'weekly',
  day_of_week: 0,
  time_of_day: '18:00:00',
  starts_at: '2026-01-01',
  ends_at: null,
  generate_days_ahead: 7,
  is_active: true,
  created_by: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  discord_notify_new_events: true,
  auto_create_hero_drafts: false,
  discord_send_draft_link: true,
  discord_send_herodraft_link: true,
  next_event_date: null,
  subscriber_count: 0,
  is_subscribed: false,
} satisfies EventRepeaterType;

export const event: EventType = {
  ...config,
  id: 11,
  organization_name: 'Org',
  event_repeater: null,
  event_repeater_name: null,
  name: 'Night 4',
  description: '',
  scheduled_at: '2026-12-01T19:00:00Z',
  signups_open_at: null,
  state: 'signups_open',
  tournament: 5,
  created_by: 1,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  signup_count: 0,
  confirmed_count: 0,
  is_off_schedule: false,
  dota_lobby_mode: 'off',
  dota_lobby_launch: 'manual',
  dota_lobby_region: '',
  discord_send_lobby_info: false,
  dota_lobby_password_mode: 'random',
  user_can_manage: true,
  ends_at: null,
  host: null,
  helpers: [],
  contributions_awarded_at: null,
  user_can_manage_event_staff: false,
};

export function openTab(name: RegExp) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), {
    button: 0,
    ctrlKey: false,
  });
}

export function submit() {
  fireEvent.click(screen.getByTestId('form-dialog-submit'));
}
