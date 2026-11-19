// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrgEventDefaultsType } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { READY_CHECK_TEST_IDS as IDS } from '../form/testIds';
import { baseOrgDefaults } from './readyCheckModalFixtures';

const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  getOrgEventDefaults: vi.fn(),
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';

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

async function renderWith(
  overrides: Partial<OrgEventDefaultsType>,
): Promise<void> {
  api.getOrgEventDefaults.mockResolvedValue({
    ...baseOrgDefaults,
    ...overrides,
  });
  render(<CreateEventModal organizationId={1} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  });
  await waitFor(() =>
    expect(screen.getByTestId('event-name-input')).toBeInTheDocument(),
  );
  fireEvent.change(screen.getByTestId('event-name-input'), {
    target: { value: 'Friday inhouse' },
  });
}

function submit(): void {
  fireEvent.click(screen.getByTestId('form-dialog-submit'));
}

async function eventBody(): Promise<Record<string, unknown>> {
  submit();
  await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
  return api.createEvent.mock.calls[0][0];
}

describe('CreateEventModal ready check', () => {
  beforeEach(() => {
    api.createEvent.mockReset().mockResolvedValue({ id: 1 });
    api.createEventRepeater.mockReset().mockResolvedValue({ id: 2 });
    api.getOrgEventDefaults.mockReset();
  });

  it('renders a Ready check tab', async () => {
    await renderWith({});
    expect(screen.getByTestId('event-modal-tab-ready')).toBeInTheDocument();
  });

  it('never inherits auto-confirm but copies the other ready check defaults', async () => {
    await renderWith({
      auto_confirm: true,
      roll_call_enabled: false,
      ready_check_open_minutes: 90,
    });
    expect(await eventBody()).toMatchObject({
      auto_confirm: false,
      roll_call_enabled: false,
      ready_check_open_minutes: 90,
    });
  });

  it('copies roll call and its mode from org defaults', async () => {
    await renderWith({ roll_call_enabled: true, roll_call_mode: 'automatic' });
    expect(await eventBody()).toMatchObject({
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
    });
  });

  it('applies the preset when the toggle is turned on', async () => {
    await renderWith({ auto_confirm: true });
    fireEvent.click(screen.getByTestId(IDS.toggle));
    expect(await eventBody()).toMatchObject({
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
      auto_confirm: false,
    });
  });

  it('sends the preset on the series path', async () => {
    await renderWith({});
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    fireEvent.click(screen.getByTestId(IDS.toggle));
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEvent).not.toHaveBeenCalled();
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject({
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
      auto_confirm: false,
      ready_check_open_minutes: 120,
      ready_check_chase_minutes: 30,
    });
  });
});
