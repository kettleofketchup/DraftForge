// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { logger, toastError } = vi.hoisted(() => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
  toastError: vi.fn(),
}));

vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));
vi.mock('sonner', () => ({ toast: { error: toastError, success: vi.fn() } }));
vi.mock('~/store/userStore', () => ({
  useUserStore: (sel: (s: { currentUser: { pk: number } }) => unknown) =>
    sel({ currentUser: { pk: 9 } }),
}));
vi.mock('../api', () => ({
  getSteamVerification: vi.fn(),
  setSteamVerification: vi.fn(),
}));

import { useUserCacheStore } from '~/store/userCacheStore';
import { getSteamVerification, setSteamVerification } from '../api';
import { useSetSteamVerification, useSteamVerification } from '../queries';
import { steamVerificationKeys } from '../queryKeys';

const verified = {
  steam_account_id: 123,
  steam_account_verified: true,
  steam_account_verified_at: '2026-11-22T10:00:00+00:00',
  steam_account_verified_org_name: 'Kettle League',
  steam_account_exists_checked: true,
  steam_profile_url: 'https://steamcommunity.com/profiles/76561197960265851',
  dotabuff_url: 'https://www.dotabuff.com/players/123',
  can_verify: true,
};

const DETAIL = steamVerificationKeys.detail(5, 9);
const RELATED = [
  ['event-signups', 1],
  ['user-dota-profile', 5, 2],
  ['dota-profile', 2, 5],
  ['tournament', 3],
] as const;

function httpError(status: number, data: unknown): AxiosError {
  const response = {
    status,
    data,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  } as AxiosResponse;
  return new AxiosError(
    `Request failed with status code ${status}`,
    String(status),
    undefined,
    undefined,
    response,
  );
}

function setup(): {
  qc: QueryClient;
  wrapper: (props: { children: ReactNode }) => ReactNode;
} {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000 },
      mutations: { retry: false },
    },
  });
  for (const key of RELATED) qc.setQueryData(key, { cached: true });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

afterEach(() => {
  vi.mocked(getSteamVerification).mockReset();
  vi.mocked(setSteamVerification).mockReset();
  toastError.mockReset();
  Object.values(logger).forEach((fn) => fn.mockReset());
});

describe('steamVerificationKeys', () => {
  it('scopes the detail by viewer under one prefix', () => {
    expect(steamVerificationKeys.all).toEqual(['steamVerification']);
    expect(steamVerificationKeys.detail(5, 9)).toEqual([
      'steamVerification',
      5,
      9,
    ]);
  });
});

describe('useSteamVerification', () => {
  it('loads the detail when enabled', async () => {
    vi.mocked(getSteamVerification).mockResolvedValue(verified);
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useSteamVerification(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toEqual(verified));
    expect(getSteamVerification).toHaveBeenCalledWith(5);
  });

  it('does not fetch when disabled', () => {
    const { wrapper } = setup();
    renderHook(() => useSteamVerification(5, { enabled: false }), {
      wrapper,
    });
    expect(getSteamVerification).not.toHaveBeenCalled();
  });

  it('treats a 403 quietly: no retry, no toast, no error log', async () => {
    vi.mocked(getSteamVerification).mockRejectedValue(
      httpError(403, { detail: 'You do not have permission.' }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useSteamVerification(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(getSteamVerification).toHaveBeenCalledTimes(1);
    expect(toastError).not.toHaveBeenCalled();
    expect(logger.error).not.toHaveBeenCalled();
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('warns on other GET errors without a toast', async () => {
    vi.mocked(getSteamVerification).mockRejectedValue(
      httpError(500, { detail: 'boom' }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useSteamVerification(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 10_000,
    });
    expect(logger.warn).toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  }, 15_000);
});

describe('useSetSteamVerification', () => {
  it('stores the reply, upserts the user and invalidates related data', async () => {
    vi.mocked(setSteamVerification).mockResolvedValue(verified);
    useUserCacheStore
      .getState()
      .upsert({ pk: 5, username: 'player', steam_account_id: 123 });
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useSetSteamVerification(5), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({ verified: true, steamAccountId: 123 });
    });
    expect(setSteamVerification).toHaveBeenCalledWith(5, true, 123);
    expect(qc.getQueryData(DETAIL)).toEqual(verified);
    for (const key of RELATED) {
      expect(qc.getQueryState(key)?.isInvalidated).toBe(true);
    }
    const entry = useUserCacheStore.getState().getById(5);
    expect(entry).toMatchObject({
      steam_account_id: 123,
      steam_account_verified: true,
      steam_account_verified_at: '2026-11-22T10:00:00+00:00',
      steam_account_verified_org_name: 'Kettle League',
      steam_account_exists_checked: true,
    });
    expect(entry?.username).toBe('player');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('does not add a partial user to the cache', async () => {
    vi.mocked(setSteamVerification).mockResolvedValue(verified);
    const { wrapper } = setup();
    const { result } = renderHook(() => useSetSteamVerification(5), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({ verified: true, steamAccountId: 123 });
    });
    expect(useUserCacheStore.getState().getById(5)).toBeUndefined();
  });

  it('on 409 id_changed refetches the detail and toasts the new-id copy', async () => {
    vi.mocked(setSteamVerification).mockRejectedValue(
      httpError(409, {
        error: 'The Friend ID changed since you loaded it',
        code: 'id_changed',
        steam_account_id: 456,
      }),
    );
    const { qc, wrapper } = setup();
    qc.setQueryData(DETAIL, verified);
    const { result } = renderHook(() => useSetSteamVerification(5), {
      wrapper,
    });
    await act(async () => {
      await result.current
        .mutateAsync({ verified: true, steamAccountId: 123 })
        .catch(() => undefined);
    });
    expect(qc.getQueryState(DETAIL)?.isInvalidated).toBe(true);
    expect(toastError).toHaveBeenCalledWith(
      'The Friend ID changed; check the new one before verifying.',
    );
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('toasts the API message and logs other errors', async () => {
    vi.mocked(setSteamVerification).mockRejectedValue(
      httpError(400, {
        error: 'User has no Friend ID',
        code: 'no_steam_account_id',
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useSetSteamVerification(5), {
      wrapper,
    });
    await act(async () => {
      await result.current
        .mutateAsync({ verified: true, steamAccountId: 123 })
        .catch(() => undefined);
    });
    expect(toastError).toHaveBeenCalledWith('User has no Friend ID');
    expect(logger.error).toHaveBeenCalled();
  });

  it('falls back to a generic toast when the error has no message', async () => {
    vi.mocked(setSteamVerification).mockRejectedValue(new Error('offline'));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSetSteamVerification(5), {
      wrapper,
    });
    await act(async () => {
      await result.current
        .mutateAsync({ verified: false, steamAccountId: 123 })
        .catch(() => undefined);
    });
    expect(toastError).toHaveBeenCalledWith('Could not update verification');
  });
});
