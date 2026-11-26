// @vitest-environment jsdom
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import type { EventType } from '../schemas';
import { baseEvent } from './readyCheckModalFixtures';

vi.mock('~/components/organization/hooks/useOrganization', () => ({
  useOrganization: () => ({ organization: null }),
}));

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({ mutateAsync, isPending: false }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));
vi.mock('../form/sections/EventTournamentFields', () => ({
  EventTournamentFields: () => null,
}));
vi.mock('../form/sections/EventLobbyFields', () => ({
  EventLobbyFields: () => null,
}));
vi.mock('../form/fields/TimezoneField', () => ({ TimezoneField: () => null }));
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
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { EditEventModal } from '../EditEventModal';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <TooltipProvider>{children}</TooltipProvider>
    </I18nextProvider>
  );
}

const seriesEvent: EventType = {
  ...baseEvent,
  event_repeater: 5,
  event_repeater_name: 'Weekly',
};

async function openDiscordTab() {
  fireEvent.mouseDown(screen.getByTestId('edit-event-tab-discord'), {
    button: 0,
  });
  await waitFor(() =>
    expect(screen.getByTestId('edit-event-tab-discord')).toHaveAttribute(
      'data-state',
      'active',
    ),
  );
}

describe('EditEventModal Discord tab', () => {
  it('hides the series-only new-event toggle on a series event', async () => {
    render(
      <EditEventModal event={seriesEvent} open onOpenChange={() => {}} />,
      {
        wrapper: Wrapper,
      },
    );
    fireEvent.mouseDown(screen.getByTestId('edit-event-tab-discord'), {
      button: 0,
    });
    await waitFor(() =>
      expect(screen.getByTestId('edit-event-tab-discord')).toHaveAttribute(
        'data-state',
        'active',
      ),
    );
    expect(
      screen.getByTestId('discord-discord_signup_reminder'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('discord-discord_notify_new_events'),
    ).toBeNull();
    expect(
      screen.queryByTestId('discord-announcement-channel-select'),
    ).toBeNull();
  });

  it('round-trips discord_new_event_channel_id while its picker is hidden', async () => {
    mutateAsync.mockClear();
    render(
      <EditEventModal
        event={{
          ...seriesEvent,
          discord_new_event_channel_id: '555',
        }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await openDiscordTab();
    expect(screen.queryByTestId('discord-new-event-channel-select')).toBeNull();
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      discord_new_event_channel_id: '555',
    });
  });

  it('round-trips toggled-off post channels', async () => {
    mutateAsync.mockClear();
    render(
      <EditEventModal
        event={{
          ...baseEvent,
          discord_confirm_attendance: false,
          discord_confirm_attendance_channel_id: '666',
          discord_profile_reminder: false,
          discord_profile_reminder_channel_id: '777',
        }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await openDiscordTab();
    expect(
      screen.queryByTestId('discord-confirm-attendance-channel-select'),
    ).toBeNull();
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      discord_confirm_attendance_channel_id: '666',
      discord_profile_reminder_channel_id: '777',
    });
  });

  it('series event shows the signup reminder DM in Direct messages', async () => {
    render(
      <EditEventModal event={seriesEvent} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await openDiscordTab();
    const group = screen.getByTestId('discord-subsection-direct-messages');
    expect(
      within(group).getByTestId('discord-discord_signup_reminder'),
    ).toBeInTheDocument();
    expect(
      within(group).getByTestId('discord-signup-reminder-subscribe-note'),
    ).toBeInTheDocument();
    expect(within(group).queryByRole('alert')).toBeNull();
    expect(
      screen.queryByTestId('discord-direct-messages-series-only'),
    ).toBeNull();
  });

  it('single event shows the series-only Direct messages line', async () => {
    render(<EditEventModal event={baseEvent} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
    await openDiscordTab();
    const group = screen.getByTestId('discord-subsection-direct-messages');
    expect(
      within(group).getByTestId('discord-direct-messages-series-only'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('discord-discord_signup_reminder')).toBeNull();
  });
});
