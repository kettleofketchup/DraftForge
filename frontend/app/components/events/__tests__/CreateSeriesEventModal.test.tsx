// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventRepeaterType } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';

// Mutation seam: the POST body is the assertion target.
const createSeriesOneOffEvent = vi.fn().mockResolvedValue({ id: 99 });
vi.mock('~/components/api/api', () => ({
  createSeriesOneOffEvent: (...args: unknown[]) => createSeriesOneOffEvent(...args),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { CreateSeriesEventModal } from '../CreateSeriesEventModal';

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// LeagueCombobox calls useMediaQuery, which jsdom does not implement.
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
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
  subscriber_count: 3,
  is_subscribed: false,
} satisfies EventRepeaterType;

function renderModal() {
  return render(
    <CreateSeriesEventModal repeater={repeater} open onOpenChange={() => {}} />,
    { wrapper: Wrapper }
  );
}

async function submitWithScheduledAt() {
  fireEvent.change(screen.getByTestId('one-off-scheduled-input'), {
    target: { value: '2026-09-30T20:00' },
  });
  fireEvent.click(screen.getByTestId('form-dialog-submit'));
  await waitFor(() => expect(createSeriesOneOffEvent).toHaveBeenCalled());
}

describe('CreateSeriesEventModal', () => {
  beforeEach(() => {
    createSeriesOneOffEvent.mockClear();
  });

  it('submits with only scheduled_at filled — the prefill covers every schema key', async () => {
    renderModal();
    await submitWithScheduledAt();

    expect(createSeriesOneOffEvent).toHaveBeenCalledWith(
      repeater.id,
      expect.objectContaining({ name: 'Sunday Turbo', timezone: 'America/New_York' })
    );
  });

  it("sends the series' discord_signup_reminder rather than a hard-coded false", async () => {
    renderModal();
    await submitWithScheduledAt();

    expect(createSeriesOneOffEvent.mock.calls[0][1]).toMatchObject({
      discord_signup_reminder: true,
    });
  });

  it('does not render the repeater-only "Message interested users" block', () => {
    renderModal();
    expect(screen.queryByText('Message interested users')).toBeNull();
  });
});
