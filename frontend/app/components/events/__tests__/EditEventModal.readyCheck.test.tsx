// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { READY_CHECK_TEST_IDS as IDS } from '../form/testIds';
import type { EventType } from '../schemas';
import { baseEvent, LEGACY_READY_CHECK } from './readyCheckModalFixtures';

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

const legacyEvent: EventType = { ...baseEvent, ...LEGACY_READY_CHECK };

function renderModal(e: EventType) {
  return render(<EditEventModal event={e} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  });
}

describe('EditEventModal ready check', () => {
  beforeEach(() => mutateAsync.mockClear());

  it('renders a Ready check tab', () => {
    renderModal(baseEvent);
    expect(screen.getByTestId('edit-event-tab-ready')).toBeInTheDocument();
  });

  it('saves a rename of a legacy event without resetting its settings', async () => {
    renderModal(legacyEvent);
    fireEvent.change(screen.getByTestId('edit-event-name-input'), {
      target: { value: 'Night 4 renamed' },
    });
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      name: 'Night 4 renamed',
      roll_call_enabled: true,
      roll_call_mode: 'manual',
      auto_confirm: true,
      ready_check_open_minutes: 45,
      ready_check_close_minutes: 15,
      ready_check_chase_minutes: null,
    });
  });

  it('sends the stored settings of an event that predates them as defaults', async () => {
    renderModal(baseEvent);
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      roll_call_enabled: false,
      auto_confirm: false,
      ready_check_open_minutes: 120,
      ready_check_chase_minutes: 30,
    });
  });

  it('blocks an edited timing that closes before it opens', async () => {
    renderModal(legacyEvent);
    fireEvent.click(screen.getByTestId(IDS.settingsTrigger));
    fireEvent.change(screen.getByTestId(IDS.close), {
      target: { value: '60' },
    });
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() =>
      expect(screen.getByTestId('edit-event-tab-ready')).toHaveAttribute(
        'data-state',
        'active',
      ),
    );
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
