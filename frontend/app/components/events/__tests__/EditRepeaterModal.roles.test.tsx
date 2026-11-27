// @vitest-environment jsdom
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventRepeaterType } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';

// Mutation seam: the PATCH body is the assertion target.
vi.mock('~/components/organization/hooks/useOrganization', () => ({
  useOrganization: () => ({ organization: null }),
}));

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventRepeaterMutation: () => ({ mutateAsync, isPending: false }),
}));

// The series' fixed password is read from its staff-only endpoint.
const savedPassword = vi.hoisted(() => ({ current: undefined as unknown }));
vi.mock('~/hooks/useLobbyPassword', () => ({
  useRepeaterLobbyPassword: () => ({ data: savedPassword.current }),
}));

vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: (p: {
    value?: string;
    onChange: (value: string) => void;
    clearable?: { label: string; fallbackChannelId?: string };
    'data-testid'?: string;
  }) => {
    const testId = p['data-testid'] ?? 'channel-picker';
    return (
      <div
        data-testid={testId}
        data-value={p.value ?? ''}
        data-clear-label={p.clearable?.label ?? ''}
        data-fallback={p.clearable?.fallbackChannelId ?? ''}
      >
        {p.clearable && p.value ? (
          <button
            type="button"
            data-testid={`${testId}-clear`}
            onClick={() => p.onChange('')}
          />
        ) : null}
      </div>
    );
  },
}));
vi.mock('../DiscordRolePicker', () => ({
  DiscordRolePicker: () => <div data-testid="role-picker" />,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { EditRepeaterModal } from '../EditRepeaterModal';
import { NEW_EVENTS_DESCRIPTION } from '../form/settingsFields';

const searchHits = (prefix: string) =>
  screen.queryAllByTestId(`${prefix}-search-hit`).map((el) => {
    const [label, section] = [...el.querySelectorAll('span')].map(
      (s) => s.textContent,
    );
    return { el, label, section };
  });

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <TestQueryClientProvider>
      <I18nextProvider i18n={createI18nInstance('en')}>
        <TooltipProvider>{children}</TooltipProvider>
      </I18nextProvider>
    </TestQueryClientProvider>
  );
}

const repeater = {
  id: 7,
  organization: 1,
  organization_name: 'Org',
  name: 'Sunday Turbo',
  description: 'Weekly turbo night',
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
  tournament_name: 'Sunday Turbo Cup',
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
  roll_call_mode: 'manual',
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
  discord_signup_reminder: true,
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
  discord_confirm_attendance_channel_id: '',
  discord_profile_reminder_channel_id: '',
  discord_new_event_channel_id: '',
  discord_announcement_hours: 24,
  discord_announcement_role_ids: ['111'],
  discord_signup_role_ids: ['222'],
  discord_start_mention: false,
  discord_start_mention_minutes: 15,
  discord_start_mention_scope: 'all_active' as const,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null,
  discord_notify_new_events: true,
  auto_create_hero_drafts: false,
  discord_send_draft_link: true,
  discord_send_herodraft_link: true,
  next_event_date: null,
  subscriber_count: 0,
  is_subscribed: false,
} satisfies EventRepeaterType;

describe('EditRepeaterModal tabs', () => {
  it('renders event, tournament, lobby and discord tabs without approval', () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    for (const tab of ['event', 'tournament', 'lobby', 'discord']) {
      expect(screen.getByTestId(`edit-series-tab-${tab}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId('edit-series-tab-approval')).toBeNull();
    expect(screen.getByTestId('edit-series-modal')).toBeInTheDocument();
  });

  it('finds ready check settings that sit in a collapsed block', () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('edit-series-search'), {
      target: { value: 'closes' },
    });
    expect(searchHits('edit-series')).toContainEqual(
      expect.objectContaining({
        label: 'Closes (minutes)',
        section: 'Ready check',
      }),
    );
  });

  it('finds the signup rule under the Event section, where this form renders it', () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('edit-series-search'), {
      target: { value: 'sign themselves' },
    });
    const sections = searchHits('edit-series').map((h) => h.section);
    expect(sections).toContain('Event');
    expect(sections).not.toContain('Approval');
  });

  it('describes the new-event toggle as a channel post', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    fireEvent.mouseDown(screen.getByTestId('edit-series-tab-discord'), {
      button: 0,
    });
    await waitFor(() =>
      expect(screen.getByTestId('edit-series-tab-discord')).toHaveAttribute(
        'data-state',
        'active',
      ),
    );
    const label = screen.getByText('Post new events');
    const block = label.closest('div.rounded-md') as HTMLElement;
    const description = within(block).getByText(NEW_EVENTS_DESCRIPTION);
    expect(description.textContent).toMatch(/announcement channel/i);
    for (const el of [label, description]) {
      expect(el.textContent).not.toMatch(/\bDM\b|subscri|cancel/i);
    }
    expect(screen.queryByText('Message interested users')).toBeNull();
    expect(screen.queryByText(/DM subscribed users/)).toBeNull();
  });

  it('finds the new-event toggle when searching for notify', () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('edit-series-search'), {
      target: { value: 'notify' },
    });
    expect(searchHits('edit-series')).toContainEqual(
      expect.objectContaining({ label: 'Post new events', section: 'Discord' }),
    );
  });
});

describe('EditRepeaterModal Discord ping roles', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    savedPassword.current = undefined;
  });

  it('submits the existing role arrays unchanged instead of clearing them', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );

    fireEvent.click(screen.getByTestId('form-dialog-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      discord_announcement_role_ids: ['111'],
      discord_signup_role_ids: ['222'],
    });
  });

  it('sends no lobby password for a random series', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      {
        wrapper: Wrapper,
      },
    );
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0][0];
    expect(body.dota_lobby_password_mode).toBe('random');
    expect(body).not.toHaveProperty('dota_lobby_password');
  });

  it("keeps a fixed series' password it could not load", async () => {
    // The staff endpoint failed or is still loading: the field stays empty,
    // and saving another change must not require retyping the password.
    render(
      <EditRepeaterModal
        repeater={{ ...repeater, dota_lobby_password_mode: 'fixed' }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('lobby-password-input')).toHaveValue('');
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0][0];
    expect(body.dota_lobby_password_mode).toBe('fixed');
    expect(body).not.toHaveProperty('dota_lobby_password');
    expect(body).not.toHaveProperty('dota_lobby_password_saved');
  });

  it("keeps a fixed series' password it loaded", async () => {
    savedPassword.current = {
      mode: 'fixed',
      password: 'series-pw',
      can_manage: true,
    };
    render(
      <EditRepeaterModal
        repeater={{ ...repeater, dota_lobby_password_mode: 'fixed' }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await waitFor(() =>
      expect(screen.getByTestId('lobby-password-input')).toHaveValue(
        'series-pw',
      ),
    );
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      dota_lobby_password_mode: 'fixed',
      dota_lobby_password: 'series-pw',
    });
  });
});

describe('EditRepeaterModal draft settings', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    savedPassword.current = undefined;
  });

  it('shows saved series timers and sends edits as flat ms fields', async () => {
    render(
      <EditRepeaterModal
        repeater={{
          ...repeater,
          draft_timer_enabled: true,
          draft_grace_time_ms: 20000,
          draft_reserve_time_ms: 40000,
          hero_timer_enabled: true,
          hero_grace_time_ms: 25000,
          hero_reserve_time_ms: 60000,
        }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('draft-settings-team-grace-s')).toHaveValue(20);
    fireEvent.click(screen.getByTestId('draft-settings-team-timer-enabled'));
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0][0];
    expect(body).toMatchObject({
      draft_timer_enabled: false,
      draft_grace_time_ms: 20000,
      draft_reserve_time_ms: 40000,
      draft_timeout_action: 'skip_turn',
      hero_timer_enabled: false,
      hero_grace_time_ms: 25000,
      hero_reserve_time_ms: 60000,
    });
    expect(body).not.toHaveProperty('draft_grace_time_s');
    expect(body).not.toHaveProperty('hero_reserve_time_s');
  });
});

describe('EditRepeaterModal signup open policy', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    savedPassword.current = undefined;
  });

  it('shows stored hours as days and submits them back unchanged', async () => {
    render(
      <EditRepeaterModal
        repeater={{
          ...repeater,
          signup_open_mode: 'scheduled',
          signups_open_hours_before: 72,
        }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('signup-open-days-input')).toHaveValue(3);
    expect(
      screen.getByText(/recalculates open times for upcoming events/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 72,
    });
  });
});
