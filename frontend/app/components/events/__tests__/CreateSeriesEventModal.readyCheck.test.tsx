// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { baseRepeater, LEGACY_READY_CHECK } from './readyCheckModalFixtures';

const createSeriesOneOffEvent = vi.fn().mockResolvedValue({ id: 99 });
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createSeriesOneOffEvent: (...args: unknown[]) =>
    createSeriesOneOffEvent(...args),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/components/lobby/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/lobby/api')>()),
  getRepeaterLobbyPassword: vi.fn().mockResolvedValue(null),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { CreateSeriesEventModal } from '../CreateSeriesEventModal';

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
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}

describe('CreateSeriesEventModal ready check', () => {
  beforeEach(() => createSeriesOneOffEvent.mockClear());

  it('creates a one-off from a legacy series without a validation block', async () => {
    render(
      <CreateSeriesEventModal
        repeater={{ ...baseRepeater, ...LEGACY_READY_CHECK }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('one-off-tab-ready')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('one-off-scheduled-input'), {
      target: { value: '2026-09-30T20:00' },
    });
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(createSeriesOneOffEvent).toHaveBeenCalled());
    expect(createSeriesOneOffEvent.mock.calls[0][1]).toMatchObject({
      roll_call_enabled: true,
      auto_confirm: true,
      ready_check_open_minutes: 45,
      ready_check_close_minutes: 15,
      ready_check_chase_minutes: null,
    });
  });
});
