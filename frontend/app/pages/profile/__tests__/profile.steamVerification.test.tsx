// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { UserProfilePage } from '~/pages/user/UserProfilePage';
import { useUserStore } from '~/store/userStore';
import { ProfilePage } from '../profile';

const api = vi.hoisted(() => ({ UpdateProfile: vi.fn(), fetchUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  UpdateProfile: api.UpdateProfile,
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

const NOT_FOUND =
  'No Steam account has Friend ID 999. Check the number on your Dota 2 profile or Steam friends page.';

function notFound(): AxiosError {
  return new AxiosError(
    'Bad Request',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status: 400,
      statusText: 'Bad Request',
      data: { error: NOT_FOUND, code: 'steam_account_not_found' },
      headers: {},
      config: { headers: new AxiosHeaders() },
    },
  );
}

function setUser(user: Partial<UserType>) {
  useUserStore.setState({
    currentUser: { pk: 5, username: 'me', ...user } as UserType,
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <ProfilePage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => cleanup());

describe('ProfilePage Friend ID verification', () => {
  it('notes an unverified Friend ID', () => {
    setUser({ steam_account_id: 123, steam_account_verified: false });
    renderPage();
    expect(screen.getByTestId('profile-friend-id-unverified').textContent).toBe(
      'Unverified: an organizer will confirm this ID.',
    );
  });

  it('shows no note once verified', () => {
    setUser({ steam_account_id: 123, steam_account_verified: true });
    renderPage();
    expect(screen.queryByTestId('profile-friend-id-unverified')).toBeNull();
  });

  it('shows no note without a Friend ID', () => {
    setUser({ steam_account_id: null });
    renderPage();
    expect(screen.queryByTestId('profile-friend-id-unverified')).toBeNull();
  });

  it('puts a steam_account_not_found error on the Friend ID field', async () => {
    setUser({ steam_account_id: null });
    api.UpdateProfile.mockRejectedValue(notFound());
    renderPage();
    fireEvent.change(screen.getByPlaceholderText('Enter your Friend ID'), {
      target: { value: '999' },
    });
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));
    await waitFor(() => expect(api.UpdateProfile).toHaveBeenCalled());
    expect(await screen.findByText(NOT_FOUND)).toBeTruthy();
  });
});

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
