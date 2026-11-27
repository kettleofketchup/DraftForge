// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import { baseRepeater, LEGACY_READY_CHECK } from './readyCheckModalFixtures';

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventRepeaterMutation: () => ({ mutateAsync, isPending: false }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useRepeaterLobbyPassword: () => ({ data: undefined }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { EditRepeaterModal } from '../EditRepeaterModal';

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

describe('EditRepeaterModal ready check', () => {
  beforeEach(() => mutateAsync.mockClear());

  it('renders a Ready check tab', () => {
    render(
      <EditRepeaterModal
        repeater={baseRepeater}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('edit-series-tab-ready')).toBeInTheDocument();
  });

  it('saves a rename of a legacy series without resetting its settings', async () => {
    render(
      <EditRepeaterModal
        repeater={{ ...baseRepeater, ...LEGACY_READY_CHECK }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('edit-series-name-input'), {
      target: { value: 'Sunday Turbo renamed' },
    });
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      name: 'Sunday Turbo renamed',
      roll_call_enabled: true,
      auto_confirm: true,
      ready_check_open_minutes: 45,
      ready_check_close_minutes: 15,
      ready_check_chase_minutes: null,
    });
  });
});
