// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import type { EventType } from '../schemas';
import { baseEvent } from './readyCheckModalFixtures';

vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
  DiscordChannelPicker: (p: { 'data-testid'?: string }) => (
    <div data-testid={p['data-testid'] ?? 'channel-picker'} />
  ),
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
});
