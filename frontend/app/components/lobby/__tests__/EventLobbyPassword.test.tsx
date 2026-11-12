// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { createI18nInstance } from '~/i18n/config';
import { getEventLobbyPassword } from '../api';
import { EventLobbyPassword } from '../EventLobbyPassword';

vi.mock('~/components/lobby/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, getEventLobbyPassword: vi.fn() };
});

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.mocked(getEventLobbyPassword).mockReset();
});

describe('EventLobbyPassword', () => {
  it('shows the password to a registered player, with a copy button', async () => {
    vi.mocked(getEventLobbyPassword).mockResolvedValue({ password: 'night-4' });
    render(<EventLobbyPassword eventId={7} lobbiesEnabled signedIn />, { wrapper: Wrapper });
    expect(await screen.findByTestId('event-lobby-password-value')).toHaveTextContent('night-4');
    expect(screen.getByTestId('event-lobby-password-copy')).toBeInTheDocument();
    expect(getEventLobbyPassword).toHaveBeenCalledWith(7);
  });

  it('shows nothing when the user may not see it', async () => {
    vi.mocked(getEventLobbyPassword).mockResolvedValue(null);
    const { container } = render(<EventLobbyPassword eventId={7} lobbiesEnabled signedIn />, {
      wrapper: Wrapper,
    });
    await vi.waitFor(() => expect(getEventLobbyPassword).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('does not ask when lobbies are off or nobody is signed in', () => {
    render(<EventLobbyPassword eventId={7} lobbiesEnabled={false} signedIn />, {
      wrapper: Wrapper,
    });
    render(<EventLobbyPassword eventId={7} lobbiesEnabled signedIn={false} />, {
      wrapper: Wrapper,
    });
    expect(getEventLobbyPassword).not.toHaveBeenCalled();
    expect(screen.queryByTestId('event-lobby-password')).not.toBeInTheDocument();
  });
});
