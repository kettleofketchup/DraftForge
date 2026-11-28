// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiTokenKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import {
  archiveConnection,
  createConnection,
  getConnection,
  issueConnectionKey,
  listConnections,
  revokeConnectionKey,
  updateConnection,
} from '../connectionApi';
import {
  useArchiveConnection,
  useConnection,
  useConnectionQueryHygiene,
  useConnections,
  useCreateConnection,
  useIssueConnectionKey,
  useRevokeConnectionKey,
  useUpdateConnection,
} from '../connectionQueries';
import { connectionKeys } from '../connectionQueryKeys';
import {
  RAW_KEY,
  apiConnection,
  browserStorageText,
  clearBrowserStorage,
} from './connectionFixtures';

vi.mock('../connectionApi', () => ({
  archiveConnection: vi.fn(),
  createConnection: vi.fn(),
  getConnection: vi.fn(),
  getConnectionRun: vi.fn(),
  issueConnectionKey: vi.fn(),
  listConnectionDeliveries: vi.fn(),
  listConnectionRuns: vi.fn(),
  listConnections: vi.fn(),
  revokeConnectionKey: vi.fn(),
  updateConnection: vi.fn(),
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

function cacheText(client: QueryClient): string {
  return JSON.stringify([
    client
      .getQueryCache()
      .getAll()
      .map((q) => [q.queryKey, q.state.data]),
    client
      .getMutationCache()
      .getAll()
      .map((m) => [m.state.data, m.state.variables, m.options.mutationKey]),
  ]);
}

afterEach(() => {
  vi.clearAllMocks();
  clearBrowserStorage();
});

describe('connectionKeys', () => {
  it('scopes every key by org and viewer under the api-token feature', () => {
    expect(connectionKeys.list(ORG, 9).slice(0, 3)).toEqual(
      apiTokenKeys.all(ORG, 9),
    );
    expect(connectionKeys.detail(ORG, 9, 12)).not.toEqual(
      connectionKeys.detail(ORG, 10, 12),
    );
    expect(connectionKeys.run(ORG, 9, 12, 'r')).toEqual([
      ...connectionKeys.detail(ORG, 9, 12),
      'run',
      'r',
    ]);
  });
});

describe('connection queries', () => {
  it('does not fetch without api access', () => {
    const { wrapper } = setup();
    renderHook(() => useConnections(ORG, makeOrgFeatureAccess()), { wrapper });
    expect(listConnections).not.toHaveBeenCalled();
  });

  it('fetches the list with an abort signal for an admin with only promotion', async () => {
    vi.mocked(listConnections).mockResolvedValue([apiConnection()]);
    const { wrapper } = setup();
    const promotionOnly = makeOrgFeatureAccess({
      viewerPk: 9,
      promotionEnabled: true,
      canUseApiTokens: true,
    });
    const { result } = renderHook(() => useConnections(ORG, promotionOnly), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(listConnections).toHaveBeenCalledWith(ORG, expect.any(AbortSignal));
  });

  it('fetches one connection only when an id is given', async () => {
    vi.mocked(getConnection).mockResolvedValue(apiConnection());
    const { wrapper } = setup();
    renderHook(() => useConnection(ORG, access, null), { wrapper });
    expect(getConnection).not.toHaveBeenCalled();
    const { result } = renderHook(() => useConnection(ORG, access, 12), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data?.id).toBe(12));
  });
});

describe('connection mutations', () => {
  it('create seeds the detail and invalidates the list', async () => {
    vi.mocked(createConnection).mockResolvedValue(apiConnection());
    const { client, wrapper, invalid } = setup();
    client.setQueryData(connectionKeys.list(ORG, 9), []);
    const { result } = renderHook(() => useCreateConnection(ORG, access), {
      wrapper,
    });
    await act(() => result.current.mutateAsync({ name: 'Ratings service' }));
    expect(client.getQueryData(connectionKeys.detail(ORG, 9, 12))).toEqual(
      apiConnection(),
    );
    expect(invalid(connectionKeys.list(ORG, 9))).toBe(true);
  });

  it('update stores the saved row and invalidates the list', async () => {
    const saved = apiConnection({ config_version: 2, name: 'Renamed' });
    vi.mocked(updateConnection).mockResolvedValue(saved);
    const { client, wrapper, invalid } = setup();
    client.setQueryData(connectionKeys.list(ORG, 9), [apiConnection()]);
    const { result } = renderHook(() => useUpdateConnection(ORG, access), {
      wrapper,
    });
    await act(() =>
      result.current.mutateAsync({
        connectionId: 12,
        patch: { config_version: 1, name: 'Renamed' },
      }),
    );
    expect(client.getQueryData(connectionKeys.detail(ORG, 9, 12))).toEqual(
      saved,
    );
    expect(invalid(connectionKeys.list(ORG, 9))).toBe(true);
  });

  it('archive and revoke store the returned row and refresh legacy tokens', async () => {
    vi.mocked(archiveConnection).mockResolvedValue(
      apiConnection({ archived_at: '2026-11-21T00:00:00Z' }),
    );
    vi.mocked(revokeConnectionKey).mockResolvedValue(apiConnection());
    const { client, wrapper, invalid } = setup();
    client.setQueryData(apiTokenKeys.tokens(ORG, 9), []);
    const archive = renderHook(() => useArchiveConnection(ORG, access), {
      wrapper,
    });
    await act(() => archive.result.current.mutateAsync(12));
    expect(
      client.getQueryData<{ archived_at: string | null }>(
        connectionKeys.detail(ORG, 9, 12),
      )?.archived_at,
    ).not.toBeNull();
    expect(invalid(apiTokenKeys.tokens(ORG, 9))).toBe(true);
    const revoke = renderHook(() => useRevokeConnectionKey(ORG, access), {
      wrapper,
    });
    await act(() => revoke.result.current.mutateAsync(12));
    expect(revokeConnectionKey).toHaveBeenCalledWith(ORG, 12);
  });

  it('issue passes the secret to the callback and keeps it out of every cache', async () => {
    vi.mocked(issueConnectionKey).mockImplementation(
      async (_org, _id, _opts, onSecret) => {
        onSecret({ id: 31, prefix: 'feedbeef', token: RAW_KEY });
        return apiConnection({ inbound_enabled: true });
      },
    );
    const { client, wrapper, invalid } = setup();
    client.setQueryData(connectionKeys.list(ORG, 9), [apiConnection()]);
    const onSecret = vi.fn();
    const { result } = renderHook(
      () => useIssueConnectionKey(ORG, access, onSecret),
      { wrapper },
    );
    await act(() =>
      result.current.mutateAsync({ connectionId: 12, rotate: false }),
    );
    expect(onSecret).toHaveBeenCalledWith(
      expect.objectContaining({ token: RAW_KEY }),
    );
    expect(cacheText(client)).not.toContain(RAW_KEY);
    expect(browserStorageText()).not.toContain(RAW_KEY);
    expect(invalid(connectionKeys.list(ORG, 9))).toBe(true);
  });
});

describe('useConnectionQueryHygiene', () => {
  it('cancels and removes the old viewer scope when the viewer changes', () => {
    const { client, wrapper } = setup();
    client.setQueryData(connectionKeys.list(ORG, 9), [apiConnection()]);
    const { rerender } = renderHook(
      ({ a }) => useConnectionQueryHygiene(ORG, a),
      { wrapper, initialProps: { a: access } },
    );
    rerender({ a: makeOrgFeatureAccess({ ...access, viewerPk: 10 }) });
    expect(client.getQueryData(connectionKeys.list(ORG, 9))).toBeUndefined();
  });

  it('removes restricted queries when access is lost', () => {
    const { client, wrapper } = setup();
    const { rerender } = renderHook(
      ({ a }) => useConnectionQueryHygiene(ORG, a),
      { wrapper, initialProps: { a: access } },
    );
    client.setQueryData(connectionKeys.detail(ORG, 9, 12), apiConnection());
    rerender({
      a: makeOrgFeatureAccess({ ...access, canUseApiTokens: false }),
    });
    expect(
      client.getQueryData(connectionKeys.detail(ORG, 9, 12)),
    ).toBeUndefined();
  });

  it('removes the old org scope when the org changes', () => {
    const { client, wrapper } = setup();
    client.setQueryData(connectionKeys.list(ORG, 9), [apiConnection()]);
    const { rerender } = renderHook(
      ({ org }) => useConnectionQueryHygiene(org, access),
      { wrapper, initialProps: { org: ORG } },
    );
    rerender({ org: ORG + 1 });
    expect(client.getQueryData(connectionKeys.list(ORG, 9))).toBeUndefined();
  });
});
