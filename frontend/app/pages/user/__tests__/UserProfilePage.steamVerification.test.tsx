// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { UserProfilePage } from '~/pages/user/UserProfilePage';
import { useUserStore } from '~/store/userStore';

const api = vi.hoisted(() => ({ fetchUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser: api.fetchUser,
}));
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), promise: vi.fn() },
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function setUser(user: Partial<UserType>) {
  useUserStore.setState({
    currentUser: { pk: 5, username: 'me', ...user } as UserType,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => cleanup());

function renderUserPage(pk: number) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/user/${pk}`]}>
          <Routes>
            <Route path="/user/:pk" element={<UserProfilePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe('UserProfilePage Friend ID note', () => {
  const unverified = {
    pk: 5,
    username: 'me',
    steam_account_id: 123,
    steam_account_verified: false,
  } as UserType;

  it('shows the owner their unverified Friend ID', async () => {
    setUser({ pk: 5 });
    api.fetchUser.mockResolvedValue(unverified);
    renderUserPage(5);
    expect(
      (await screen.findByTestId('profile-friend-id-unverified')).textContent,
    ).toBe('Unverified: an organizer will confirm this ID.');
  });

  it('never shows the note to other viewers', async () => {
    setUser({ pk: 9 });
    api.fetchUser.mockResolvedValue(unverified);
    renderUserPage(5);
    expect(await screen.findByText('123')).toBeTruthy();
    expect(screen.queryByTestId('profile-friend-id-unverified')).toBeNull();
  });
});
