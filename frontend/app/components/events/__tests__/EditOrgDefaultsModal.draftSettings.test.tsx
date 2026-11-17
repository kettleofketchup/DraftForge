// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateOrgDefaultsMutation: () => ({ mutateAsync, isPending: false }),
}));

const defaults = vi.hoisted(() => ({
  id: 3,
  organization: 1,
  tournament_name: 'Weekly Cup',
  tournament_type: 'double_elimination',
  game_type: 1,
  draft_type: 'shuffle',
  people_per_team: 5,
  number_of_teams: null,
  timezone: 'America/New_York',
  game_mode: 'normal',
  max_players: null,
  auto_approve: false,
  auto_confirm: false,
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
  draft_timer_enabled: true,
  draft_grace_time_ms: 20000,
  draft_reserve_time_ms: 40000,
  draft_timeout_action: 'skip_turn',
  hero_timer_enabled: true,
  hero_grace_time_ms: 25000,
  hero_reserve_time_ms: 60000,
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getOrgEventDefaults: vi.fn().mockResolvedValue(defaults),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { EditOrgDefaultsModal } from '../EditOrgDefaultsModal';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

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

describe('EditOrgDefaultsModal tabs', () => {
  it('renders event, tournament, lobby and discord tabs without approval', async () => {
    render(
      <EditOrgDefaultsModal organizationId={1} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await waitFor(() =>
      expect(screen.getByTestId('org-defaults-tab-event')).toBeInTheDocument(),
    );
    for (const tab of ['tournament', 'lobby', 'discord']) {
      expect(screen.getByTestId(`org-defaults-tab-${tab}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId('org-defaults-tab-approval')).toBeNull();
  });
});

describe('EditOrgDefaultsModal draft settings', () => {
  beforeEach(() => mutateAsync.mockClear());

  it('shows saved default timers and sends edits as flat ms fields', async () => {
    render(
      <EditOrgDefaultsModal organizationId={1} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await waitFor(() =>
      expect(screen.getByTestId('draft-settings-team-grace-s')).toHaveValue(20),
    );
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    fireEvent.click(screen.getByTestId('form-dialog-submit'));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const { id, data } = mutateAsync.mock.calls[0][0];
    expect(id).toBe(3);
    expect(data).toMatchObject({
      draft_timer_enabled: true,
      draft_grace_time_ms: 20000,
      draft_reserve_time_ms: 40000,
      draft_timeout_action: 'skip_turn',
      hero_timer_enabled: false,
      hero_grace_time_ms: 25000,
      hero_reserve_time_ms: 60000,
    });
    expect(data).not.toHaveProperty('draft_grace_time_s');
    expect(data).not.toHaveProperty('hero_reserve_time_s');
  });
});
