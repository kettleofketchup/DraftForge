// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { UserProfilePage } from '../UserProfilePage';

const fetchUser = vi.hoisted(() => vi.fn());
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser,
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

beforeEach(() => {
  useUserCacheStore.getState().reset();
  useUserStore.setState({
    currentUser: { pk: 2, username: 'viewer' },
  } as never);
  fetchUser.mockResolvedValue({
    pk: 1,
    username: 'dc_handle',
    discordNickname: 'GwaihirTheWindlord',
  });
});

function renderProfile() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter initialEntries={['/user/1']}>
          <Routes>
            <Route path="/user/:pk" element={<UserProfilePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe('UserProfilePage names', () => {
  it('shows the global name with the username handle', async () => {
    renderProfile();
    const header = await screen.findByTestId('user-card-display-name');
    expect(header.textContent).toBe('GwaihirTheWindlord');
    expect(screen.getByText('@dc_handle')).toBeTruthy();
    expect(screen.getByText('Discord name')).toBeTruthy();
    expect(screen.queryByText('Nickname')).toBeNull();
  });
});
