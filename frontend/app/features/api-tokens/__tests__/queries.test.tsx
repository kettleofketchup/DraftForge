// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiTokenKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import {
  createApiToken,
  listApiTokens,
  putApiLimits,
  revokeApiToken,
} from '../api';
import {
  useApiTokens,
  useCreateApiToken,
  useRevokeApiToken,
  useSetApiLimits,
} from '../queries';
import { apiToken, createdApiToken } from './fixtures';

vi.mock('../api', () => ({
  createApiToken: vi.fn(),
  getApiLimits: vi.fn(),
  getApiUsage: vi.fn(),
  listApiTokens: vi.fn(),
  putApiLimits: vi.fn(),
  revokeApiToken: vi.fn(),
}));

const ORG = 4;
const access = makeOrgFeatureAccess({
  viewerPk: 9,
  mmrSyncEnabled: true,
  canUseMmrSync: true,
  canUseApiTokens: true,
});

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { client, wrapper, invalid };
}

afterEach(() => {
  vi.mocked(listApiTokens).mockReset();
  vi.mocked(createApiToken).mockReset();
  vi.mocked(revokeApiToken).mockReset();
  vi.mocked(putApiLimits).mockReset();
});

describe('useApiTokens', () => {
  it('does not fetch without mmr sync access', () => {
    const { wrapper } = setup();
    renderHook(() => useApiTokens(ORG, makeOrgFeatureAccess()), { wrapper });
    expect(listApiTokens).not.toHaveBeenCalled();
  });

  it('fetches for an admin with only promotion unlocked', async () => {
    vi.mocked(listApiTokens).mockResolvedValue([]);
    const { wrapper } = setup();
    renderHook(
      () =>
        useApiTokens(
          ORG,
          makeOrgFeatureAccess({
            viewerPk: 9,
            promotionEnabled: true,
            canUseApiTokens: true,
          }),
        ),
      { wrapper },
    );
    await waitFor(() => expect(listApiTokens).toHaveBeenCalledWith(ORG));
  });

  it('fetches with access', async () => {
    vi.mocked(listApiTokens).mockResolvedValue([apiToken()]);
    const { wrapper } = setup();
    const { result } = renderHook(() => useApiTokens(ORG, access), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(listApiTokens).toHaveBeenCalledWith(ORG);
  });
});

describe('mutations', () => {
  it('create invalidates the token list', async () => {
    vi.mocked(createApiToken).mockResolvedValue(createdApiToken());
    const { client, wrapper, invalid } = setup();
    const key = apiTokenKeys.tokens(ORG, 9);
    client.setQueryData(key, []);
    const { result } = renderHook(() => useCreateApiToken(ORG, access), {
      wrapper,
    });
    const input = { name: 'bot', operations: ['promotion:import'] };
    await act(() => result.current.mutateAsync(input));
    expect(createApiToken).toHaveBeenCalledWith(ORG, input);
    expect(invalid(key)).toBe(true);
  });

  it('revoke swaps the revoked row in and invalidates', async () => {
    const revoked = apiToken({ revoked_at: '2026-11-03T00:00:00Z' });
    vi.mocked(revokeApiToken).mockResolvedValue(revoked);
    const { client, wrapper, invalid } = setup();
    const key = apiTokenKeys.tokens(ORG, 9);
    client.setQueryData(key, [apiToken(), apiToken({ id: 2 })]);
    const { result } = renderHook(() => useRevokeApiToken(ORG, access), {
      wrapper,
    });
    await act(() => result.current.mutateAsync(1));
    expect(client.getQueryData(key)).toEqual([revoked, apiToken({ id: 2 })]);
    expect(invalid(key)).toBe(true);
  });

  it('setting limits stores them and invalidates usage', async () => {
    vi.mocked(putApiLimits).mockResolvedValue({ per_minute: 5, per_day: 50 });
    const { client, wrapper, invalid } = setup();
    const usageKey = apiTokenKeys.usage(ORG, 9, 30);
    client.setQueryData(usageKey, {});
    const { result } = renderHook(() => useSetApiLimits(ORG, access), {
      wrapper,
    });
    await act(() => result.current.mutateAsync({ per_minute: 5, per_day: 50 }));
    expect(client.getQueryData(apiTokenKeys.limits(ORG, 9))).toEqual({
      per_minute: 5,
      per_day: 50,
    });
    expect(invalid(usageKey)).toBe(true);
  });
});
