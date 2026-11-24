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
import { MemoryRouter } from 'react-router';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { SharedPopoverRenderer } from '~/components/ui/shared-popover-renderer';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { resetGameType, withGameType } from '~/test-utils/gameType';
import { PlayerPopoverTrigger } from '../PlayerPopoverTrigger';

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({
  default: { get: http.get, post: http.post },
}));
const api = vi.hoisted(() => ({ fetchUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser: api.fetchUser,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('~/components/player/PlayerLeagueSummary', () => ({
  PlayerLeagueSummary: () => null,
}));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const DETAIL_URL = '/users/42/steam-verification/';

const player = {
  pk: 42,
  username: 'alice',
  nickname: 'Alice',
  steam_account_id: 123456,
  steam_account_verified: false,
  steam_account_exists_checked: true,
} as UserType;

function detail(overrides: Record<string, unknown> = {}) {
  return {
    steam_account_id: 123456,
    steam_account_verified: false,
    steam_account_verified_at: null,
    steam_account_verified_org_name: null,
    steam_account_exists_checked: true,
    steam_profile_url: 'https://steamcommunity.com/profiles/76561197960389184',
    dotabuff_url: 'https://www.dotabuff.com/players/123456',
    can_verify: true,
    ...overrides,
  };
}

function forbidden(): AxiosError {
  return new AxiosError('Forbidden', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: 403,
    statusText: 'Forbidden',
    data: { detail: 'nope' },
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

function setViewer(viewer: Partial<UserType>) {
  useUserStore.setState({
    currentUser: { pk: 1, username: 'viewer', ...viewer } as UserType,
  });
}

function open() {
  withGameType(null);
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <SharedPopoverProvider>
            <PlayerPopoverTrigger player={player}>open</PlayerPopoverTrigger>
            <SharedPopoverRenderer />
          </SharedPopoverProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'View profile for Alice' }),
  );
}

function detailCalls(): number {
  return http.get.mock.calls.filter(([url]) => url === DETAIL_URL).length;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchUser.mockResolvedValue(player);
  http.get.mockResolvedValue({ data: detail() });
  useUserCacheStore.getState().reset?.();
  useOrgStore.setState({ currentOrg: null });
  useLeagueStore.setState({ currentLeague: null });
});

afterEach(async () => {
  cleanup();
  await new Promise((resolve) => setTimeout(resolve, 0));
  resetGameType();
});

describe('PlayerModal Friend ID verification', () => {
  it('site staff (not superuser) reach the detail query and see Verify', async () => {
    setViewer({ is_staff: true, is_superuser: false });
    open();
    expect(await screen.findByTestId('steam-verify-button')).toBeTruthy();
    expect(detailCalls()).toBeGreaterThan(0);
    expect(
      screen.getByTestId('steam-verification-unverified').textContent,
    ).toBe('Unverified');
  });

  it('Verify posts the server Friend ID', async () => {
    setViewer({ is_staff: true });
    http.post.mockResolvedValue({
      data: detail({
        steam_account_verified: true,
        steam_account_verified_at: '2026-11-22T10:00:00Z',
      }),
    });
    open();
    fireEvent.click(await screen.findByTestId('steam-verify-button'));
    await waitFor(() =>
      expect(http.post).toHaveBeenCalledWith(DETAIL_URL, {
        verified: true,
        steam_account_id: 123456,
      }),
    );
    expect(
      await screen.findByTestId('steam-verification-verified'),
    ).toBeTruthy();
  });

  it('hides verify on own row', async () => {
    setViewer({ pk: 42, is_staff: true, is_superuser: true });
    http.get.mockResolvedValue({ data: detail({ can_verify: false }) });
    open();
    await waitFor(() => expect(detailCalls()).toBeGreaterThan(0));
    expect(
      await screen.findByTestId('steam-verification-unverified'),
    ).toBeTruthy();
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
  });

  it('org staff 403 falls back to the user payload', async () => {
    setViewer({ staff_organization_ids: [3] });
    http.get.mockImplementation((url: string) =>
      url === DETAIL_URL
        ? Promise.reject(forbidden())
        : Promise.resolve({ data: detail() }),
    );
    open();
    await waitFor(() => expect(detailCalls()).toBe(1));
    expect(
      await screen.findByTestId('steam-verification-unverified'),
    ).toBeTruthy();
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(detailCalls()).toBe(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('plain members never query and see no badge', async () => {
    setViewer({});
    open();
    expect(await screen.findByTestId('player-modal-friend-id')).toBeTruthy();
    expect(detailCalls()).toBe(0);
    expect(screen.queryByTestId('steam-verification-unverified')).toBeNull();
  });
});
