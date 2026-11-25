// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import { getBotAccess, refreshBotAccess, retryAfterSeconds } from '../api';
import { botAccessKeys, useBotAccess, useRefreshBotAccess } from '../queries';
import { makeRow, makeSnapshot } from './fixtures';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

const LEAGUE = 7;

function httpError(status: number, headers: Record<string, string> = {}) {
  const response = {
    status,
    statusText: '',
    data: {},
    headers: new AxiosHeaders(headers),
    config: { headers: new AxiosHeaders() },
  };
  return new AxiosError(
    `Request failed with status code ${status}`,
    'ERR_BAD_RESPONSE',
    undefined,
    undefined,
    response,
  );
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

afterEach(() => {
  get.mockReset();
  post.mockReset();
});

describe('bot access api', () => {
  it('gets and parses the snapshot', async () => {
    get.mockResolvedValue({ data: makeSnapshot() });
    await expect(getBotAccess(LEAGUE)).resolves.toEqual(makeSnapshot());
    expect(get).toHaveBeenCalledWith('/leagues/7/bot-access/');
  });

  it('posts the refresh and parses the snapshot', async () => {
    const snapshot = makeSnapshot({ refresh_outcome: 'ok' });
    post.mockResolvedValue({ data: snapshot });
    await expect(refreshBotAccess(LEAGUE)).resolves.toEqual(snapshot);
    expect(post).toHaveBeenCalledWith('/leagues/7/bot-access/refresh/');
  });

  it('rejects an invalid body', async () => {
    get.mockResolvedValue({ data: { provider: 'dota2' } });
    await expect(getBotAccess(LEAGUE)).rejects.toBeInstanceOf(ZodError);
  });
});

describe('retryAfterSeconds', () => {
  it('reads the header of a 429', () => {
    expect(retryAfterSeconds(httpError(429, { 'Retry-After': '12' }))).toBe(12);
  });

  it('returns null for other errors', () => {
    expect(retryAfterSeconds(httpError(500, { 'Retry-After': '12' }))).toBe(
      null,
    );
    expect(retryAfterSeconds(httpError(429))).toBe(null);
    expect(retryAfterSeconds(httpError(429, { 'Retry-After': 'soon' }))).toBe(
      null,
    );
    expect(retryAfterSeconds(new Error('boom'))).toBe(null);
    expect(retryAfterSeconds(undefined)).toBe(null);
  });
});

describe('useBotAccess', () => {
  it('does not fetch when disabled', () => {
    const { wrapper } = setup();
    renderHook(() => useBotAccess(LEAGUE, false), { wrapper });
    renderHook(() => useBotAccess(undefined, true), { wrapper });
    expect(get).not.toHaveBeenCalled();
  });

  it('fetches and parses the snapshot', async () => {
    get.mockResolvedValue({ data: makeSnapshot() });
    const { wrapper, client } = setup();
    const { result } = renderHook(() => useBotAccess(LEAGUE, true), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(makeSnapshot());
    expect(client.getQueryData(botAccessKeys.league(LEAGUE))).toEqual(
      makeSnapshot(),
    );
  });

  it('surfaces a Zod-invalid body as an error', async () => {
    get.mockResolvedValue({ data: { bots: 'nope' } });
    const { wrapper } = setup();
    const { result } = renderHook(() => useBotAccess(LEAGUE, true), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ZodError);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it.each([400, 404, 429])('does not retry a %i', async (status) => {
    get.mockRejectedValue(httpError(status, { 'Retry-After': '5' }));
    const { wrapper } = setup();
    const { result } = renderHook(() => useBotAccess(LEAGUE, true), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(get).toHaveBeenCalledTimes(1);
  });
});

describe('useRefreshBotAccess', () => {
  it('replaces the cached snapshot', async () => {
    const refreshed = makeSnapshot({
      refresh_outcome: 'ok',
      bots: [makeRow({ refresh: 'ok' })],
      held_count: 1,
    });
    post.mockResolvedValue({ data: refreshed });
    const { wrapper, client } = setup();
    client.setQueryData(botAccessKeys.league(LEAGUE), makeSnapshot());
    const { result } = renderHook(() => useRefreshBotAccess(LEAGUE), {
      wrapper,
    });
    await act(() => result.current.mutateAsync());
    expect(client.getQueryData(botAccessKeys.league(LEAGUE))).toEqual(
      refreshed,
    );
    await waitFor(() => expect(result.current.data).toEqual(refreshed));
  });

  it('cancels an in-flight GET so its late result is dropped', async () => {
    let resolveGet: (value: unknown) => void = () => {};
    get.mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve;
      }),
    );
    const refreshed = makeSnapshot({
      refresh_outcome: 'timed_out',
      bots: [makeRow({ refresh: 'not_ready' })],
    });
    post.mockResolvedValue({ data: refreshed });
    const { wrapper, client } = setup();
    const { result } = renderHook(
      () => ({
        query: useBotAccess(LEAGUE, true),
        refresh: useRefreshBotAccess(LEAGUE),
      }),
      { wrapper },
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));

    await act(() => result.current.refresh.mutateAsync());
    await act(async () => {
      resolveGet({ data: makeSnapshot() });
    });

    expect(client.getQueryData(botAccessKeys.league(LEAGUE))).toEqual(
      refreshed,
    );
    await waitFor(() => expect(result.current.query.data).toEqual(refreshed));
    expect(get).toHaveBeenCalledTimes(1);
    expect(result.current.refresh.data?.refresh_outcome).toBe('timed_out');
    expect(result.current.refresh.data?.bots[0]?.refresh).toBe('not_ready');
  });
});
