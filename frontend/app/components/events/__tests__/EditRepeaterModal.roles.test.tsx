// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventRepeaterType } from '~/components/api/api';
import { I18nextProvider } from 'react-i18next';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';

// Mutation seam: the PATCH body is the assertion target.
const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventRepeaterMutation: () => ({ mutateAsync, isPending: false }),
}));

// The series' fixed password is read from its staff-only endpoint.
const savedPassword = vi.hoisted(() => ({ current: undefined as unknown }));
vi.mock('~/hooks/useLobbyPassword', () => ({
  useRepeaterLobbyPassword: () => ({ data: savedPassword.current }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { EditRepeaterModal } from '../EditRepeaterModal';

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <TooltipProvider>{children}</TooltipProvider>
    </I18nextProvider>
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
  roll_call_mode: 'none',
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
  discord_announcement_hours: 24,
  discord_announcement_role_ids: ['111'],
  discord_signup_role_ids: ['222'],
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

describe('EditRepeaterModal Discord ping roles', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    savedPassword.current = undefined;
  });

  it('submits the existing role arrays unchanged instead of clearing them', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper }
    );

    fireEvent.click(screen.getByTestId('form-dialog-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      discord_announcement_role_ids: ['111'],
      discord_signup_role_ids: ['222'],
    });
  });

  it('sends no lobby password for a random series', async () => {
    render(<EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
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
    savedPassword.current = { mode: 'fixed', password: 'series-pw', can_manage: true };
    render(
      <EditRepeaterModal
        repeater={{ ...repeater, dota_lobby_password_mode: 'fixed' }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await waitFor(() =>
      expect(screen.getByTestId('lobby-password-input')).toHaveValue('series-pw'),
    );
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      dota_lobby_password_mode: 'fixed',
      dota_lobby_password: 'series-pw',
    });
  });
});
