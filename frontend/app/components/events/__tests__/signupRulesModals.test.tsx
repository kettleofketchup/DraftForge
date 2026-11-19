// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  EventRepeaterType,
  OrgEventDefaultsType,
} from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { READY_CHECK_CONFIG_DEFAULTS, type EventType } from '../schemas';

// Every write seam the five modals use; the body is the assertion target.
const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  createSeriesOneOffEvent: vi.fn(),
  getOrgEventDefaults: vi.fn(),
  mutateAsync: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  createEventRepeater: api.createEventRepeater,
  createSeriesOneOffEvent: api.createSeriesOneOffEvent,
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateEventRepeaterMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateOrgDefaultsMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRepeaterLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';
import { CreateSeriesEventModal } from '../CreateSeriesEventModal';
import { EditEventModal } from '../EditEventModal';
import { EditOrgDefaultsModal } from '../EditOrgDefaultsModal';
import { EditRepeaterModal } from '../EditRepeaterModal';

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

function Wrapper({ children }: { children: React.ReactNode }) {
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

const ROSTER_LABEL = 'Mandatory RSVP Confirmation';
const SELF_SERVE_LABEL = 'Members can sign themselves up';

const config = {
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
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
};

const orgDefaults = { id: 3, ...config } satisfies OrgEventDefaultsType;

const repeater = {
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

const event: EventType = {
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

function openTab(name: RegExp) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), {
    button: 0,
    ctrlKey: false,
  });
}

async function toggleRules(selfServeTab: RegExp = /approval/i) {
  openTab(/ready check/i);
  fireEvent.click(await screen.findByLabelText(ROSTER_LABEL));
  openTab(selfServeTab);
  fireEvent.click(await screen.findByLabelText(SELF_SERVE_LABEL));
}

async function expectRules(roster: boolean, selfServe: boolean) {
  openTab(/ready check/i);
  const rosterSwitch = await screen.findByLabelText(ROSTER_LABEL);
  expect(rosterSwitch.getAttribute('aria-checked')).toBe(String(roster));
  openTab(/approval/i);
  const selfServeBox = await screen.findByLabelText(SELF_SERVE_LABEL);
  if (selfServe) expect(selfServeBox).toBeChecked();
  else expect(selfServeBox).not.toBeChecked();
}

const TOGGLED = { roll_call_enabled: true, allow_user_signups: false };

function submit() {
  fireEvent.click(screen.getByTestId('form-dialog-submit'));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.createEventRepeater.mockResolvedValue({ id: 98 });
  api.createSeriesOneOffEvent.mockResolvedValue({ id: 97 });
  api.mutateAsync.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('CreateEventModal signup rules', () => {
  async function renderReady() {
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(await screen.findByTestId('event-name-input'), {
      target: { value: 'Night 5' },
    });
  }

  it('starts from the org defaults', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      roll_call_enabled: true,
      allow_user_signups: false,
    });
    await renderReady();
    await expectRules(true, false);
  });

  it('sends both flags for a single event', async () => {
    await renderReady();
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
    expect(api.createEvent.mock.calls[0][0]).toMatchObject(TOGGLED);
  });

  it('sends both flags for a recurring series', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('CreateSeriesEventModal signup rules', () => {
  it("starts from the series' flags and sends the toggled values", async () => {
    render(
      <CreateSeriesEventModal
        repeater={{ ...repeater, allow_user_signups: false }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('one-off-scheduled-input'), {
      target: { value: '2026-09-30T20:00' },
    });
    await expectRules(false, false);
    openTab(/ready check/i);
    fireEvent.click(await screen.findByLabelText(ROSTER_LABEL));
    submit();
    await waitFor(() => expect(api.createSeriesOneOffEvent).toHaveBeenCalled());
    expect(api.createSeriesOneOffEvent.mock.calls[0][1]).toMatchObject(TOGGLED);
  });
});

describe('EditEventModal signup rules', () => {
  it("starts from the event's flags", async () => {
    render(
      <EditEventModal
        event={{ ...event, roll_call_enabled: true }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await expectRules(true, true);
  });

  it('sends the toggled flags', async () => {
    render(<EditEventModal event={event} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
    await toggleRules();
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('EditRepeaterModal signup rules', () => {
  it('sends the toggled flags', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await toggleRules(/^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('EditOrgDefaultsModal signup rules', () => {
  it('sends the toggled flags', async () => {
    render(
      <EditOrgDefaultsModal organizationId={1} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(api.getOrgEventDefaults).toHaveBeenCalled());
    await screen.findByDisplayValue('Night Cup');
    await toggleRules(/^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      id: orgDefaults.id,
      data: TOGGLED,
    });
  });
});
