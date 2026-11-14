// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import type { EventType } from '../schemas';

// Mutation seam: the PATCH body is the assertion target.
const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({ mutateAsync, isPending: false }),
}));

// The event's password is read from its staff-only endpoint.
const savedPassword = vi.hoisted(() => ({ current: undefined as unknown }));
const regenerate = vi.hoisted(() => vi.fn());
vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: savedPassword.current }),
  useRegenerateEventLobbyPassword: () => ({ mutateAsync: regenerate, isPending: false }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { EditEventModal } from '../EditEventModal';

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

const event: EventType = {
  id: 11,
  organization: 1,
  organization_name: 'Org',
  event_repeater: null,
  event_repeater_name: null,
  name: 'Night 4',
  description: '',
  scheduled_at: '2026-12-01T19:00:00Z',
  signups_open_at: null,
  state: 'upcoming',
  tournament: 5,
  created_by: 1,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  signup_count: 0,
  confirmed_count: 0,
  tournament_name: 'Night 4 Cup',
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
  is_off_schedule: false,
  dota_lobby_mode: 'auto',
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

const fixedEvent: EventType = { ...event, dota_lobby_password_mode: 'fixed' };

function renderModal(e: EventType) {
  return render(<EditEventModal event={e} open onOpenChange={() => {}} />, { wrapper: Wrapper });
}

async function submittedBody() {
  fireEvent.click(screen.getByTestId('form-dialog-submit'));
  await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  return mutateAsync.mock.calls[0][0];
}

describe('EditEventModal lobby password', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    regenerate.mockReset();
    savedPassword.current = undefined;
  });

  it('prefills a fixed password from the staff endpoint and sends it', async () => {
    savedPassword.current = { mode: 'fixed', password: 'night4', source: 'event', can_manage: true };
    renderModal(fixedEvent);
    await waitFor(() => expect(screen.getByTestId('lobby-password-input')).toHaveValue('night4'));
    expect(await submittedBody()).toMatchObject({
      dota_lobby_password_mode: 'fixed',
      dota_lobby_password: 'night4',
    });
  });

  it('keeps a fixed password it could not load instead of blocking the save', async () => {
    renderModal(fixedEvent);
    expect(screen.getByTestId('lobby-password-input')).toHaveValue('');
    const body = await submittedBody();
    expect(body.dota_lobby_password_mode).toBe('fixed');
    expect(body).not.toHaveProperty('dota_lobby_password');
    expect(body).not.toHaveProperty('dota_lobby_password_saved');
  });

  it('refills the fixed password after the event prop changes', async () => {
    savedPassword.current = { mode: 'fixed', password: 'night4', source: 'event', can_manage: true };
    const { rerender } = renderModal(fixedEvent);
    await waitFor(() => expect(screen.getByTestId('lobby-password-input')).toHaveValue('night4'));
    rerender(
      <EditEventModal event={{ ...fixedEvent, name: 'Night 4 (moved)' }} open onOpenChange={() => {}} />,
    );
    await waitFor(() => expect(screen.getByTestId('lobby-password-input')).toHaveValue('night4'));
  });

  it('sends no password in random mode', async () => {
    savedPassword.current = { mode: 'random', password: 'abcd2345wxyz', source: 'event', can_manage: true };
    renderModal(event);
    const body = await submittedBody();
    expect(body.dota_lobby_password_mode).toBe('random');
    expect(body).not.toHaveProperty('dota_lobby_password');
  });

  it('regenerates a random password', async () => {
    savedPassword.current = { mode: 'random', password: 'abcd2345wxyz', source: 'event', can_manage: true };
    regenerate.mockResolvedValue({ mode: 'random', password: 'newpw2345abc', can_manage: true });
    renderModal(event);
    fireEvent.click(screen.getByTestId('lobby-password-regenerate'));
    await waitFor(() => expect(regenerate).toHaveBeenCalledOnce());
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('notes the series cascade on an on-schedule series event only', () => {
    savedPassword.current = { mode: 'fixed', password: 'night4', source: 'event', can_manage: true };
    const { unmount } = renderModal({ ...fixedEvent, event_repeater: 3 });
    expect(screen.getByTestId('lobby-password-from-series')).toHaveTextContent(/overrides its series/);
    unmount();
    renderModal({ ...fixedEvent, event_repeater: 3, is_off_schedule: true });
    expect(screen.queryByTestId('lobby-password-from-series')).not.toBeInTheDocument();
  });
});
