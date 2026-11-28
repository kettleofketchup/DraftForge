import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, post, patch, del } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

vi.mock('~/components/api/axios', () => ({
  default: { get, post, patch, delete: del },
}));

import {
  archiveConnection,
  createConnection,
  getConnection,
  getConnectionRun,
  issueConnectionKey,
  listConnectionDeliveries,
  listConnectionRuns,
  listConnections,
  revokeConnectionKey,
  updateConnection,
} from '../connectionApi';
import {
  RAW_KEY,
  apiConnection,
  apiConnectionWire,
  connectionCredential,
  connectionRun,
} from './connectionFixtures';

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  patch.mockReset();
  del.mockReset();
});

describe('connection api', () => {
  it('lists connections with an abort signal', async () => {
    get.mockResolvedValue({ data: [apiConnectionWire()] });
    const controller = new AbortController();
    await expect(listConnections(7, controller.signal)).resolves.toEqual([
      apiConnection(),
    ]);
    expect(get).toHaveBeenCalledWith('/organizations/7/api-connections/', {
      signal: controller.signal,
    });
  });

  it('rejects a malformed list', async () => {
    get.mockResolvedValue({ data: [{ id: 'x' }] });
    await expect(listConnections(7)).rejects.toBeInstanceOf(ZodError);
  });

  it('gets one connection and rejects a malformed body', async () => {
    get.mockResolvedValueOnce({ data: apiConnectionWire() });
    await expect(getConnection(7, 12)).resolves.toEqual(apiConnection());
    expect(get).toHaveBeenCalledWith('/organizations/7/api-connections/12/', {
      signal: undefined,
    });
    get.mockResolvedValueOnce({ data: { ...apiConnectionWire(), name: 3 } });
    await expect(getConnection(7, 12)).rejects.toBeInstanceOf(ZodError);
  });

  it('creates and patches with the given body', async () => {
    post.mockResolvedValue({ data: apiConnectionWire() });
    await createConnection(7, { name: 'Ratings service' });
    expect(post).toHaveBeenCalledWith('/organizations/7/api-connections/', {
      name: 'Ratings service',
    });
    patch.mockResolvedValue({ data: apiConnectionWire({ config_version: 2 }) });
    const saved = await updateConnection(7, 12, {
      config_version: 1,
      name: 'Renamed',
    });
    expect(saved.config_version).toBe(2);
    expect(patch).toHaveBeenCalledWith('/organizations/7/api-connections/12/', {
      config_version: 1,
      name: 'Renamed',
    });
  });

  it('archives with DELETE', async () => {
    del.mockResolvedValue({
      data: apiConnectionWire({ archived_at: '2026-11-21T00:00:00Z' }),
    });
    const row = await archiveConnection(7, 12);
    expect(row.archived_at).not.toBeNull();
    expect(del).toHaveBeenCalledWith('/organizations/7/api-connections/12/');
  });

  it('hands the raw key to the callback once and returns only redacted metadata', async () => {
    const connection = apiConnectionWire({
      inbound_enabled: true,
      operations: ['mmr:read'],
      inbound_credentials: [connectionCredential()],
    });
    post.mockResolvedValue({
      data: {
        connection,
        credential: { id: 31, prefix: 'feedbeef', token: RAW_KEY },
      },
    });
    const onSecret = vi.fn();
    const result = await issueConnectionKey(7, 12, { rotate: false }, onSecret);
    expect(onSecret).toHaveBeenCalledTimes(1);
    expect(onSecret).toHaveBeenCalledWith({
      id: 31,
      prefix: 'feedbeef',
      token: RAW_KEY,
    });
    expect(JSON.stringify(result)).not.toContain(RAW_KEY);
    expect(result.id).toBe(12);
    expect(post).toHaveBeenCalledWith(
      '/organizations/7/api-connections/12/issue-key/',
      {},
    );
  });

  it('rotates with confirmed grants and rejects a key response without a token', async () => {
    post.mockResolvedValueOnce({
      data: {
        connection: apiConnectionWire(),
        credential: { id: 31, prefix: 'feedbeef', token: RAW_KEY },
      },
    });
    await issueConnectionKey(
      7,
      12,
      { rotate: true, confirmed_operations: ['promotion:import'] },
      vi.fn(),
    );
    expect(post).toHaveBeenCalledWith(
      '/organizations/7/api-connections/12/rotate-key/',
      { confirmed_operations: ['promotion:import'] },
    );
    post.mockResolvedValueOnce({
      data: {
        connection: apiConnectionWire(),
        credential: { id: 31, prefix: 'feedbeef' },
      },
    });
    const onSecret = vi.fn();
    await expect(
      issueConnectionKey(7, 12, { rotate: false }, onSecret),
    ).rejects.toBeInstanceOf(ZodError);
    expect(onSecret).not.toHaveBeenCalled();
  });

  it('revokes the key', async () => {
    post.mockResolvedValue({ data: apiConnectionWire() });
    await revokeConnectionKey(7, 12);
    expect(post).toHaveBeenCalledWith(
      '/organizations/7/api-connections/12/revoke-key/',
      {},
    );
  });

  it('reads runs, one run and deliveries', async () => {
    get.mockResolvedValueOnce({
      data: { items: [connectionRun()], next_cursor: 'abc' },
    });
    const page = await listConnectionRuns(7, 12, 'prev');
    expect(page.next_cursor).toBe('abc');
    expect(get).toHaveBeenLastCalledWith(
      '/organizations/7/api-connections/12/runs/',
      { params: { cursor: 'prev' }, signal: undefined },
    );
    get.mockResolvedValueOnce({ data: { ...connectionRun(), issues: [] } });
    const run = await getConnectionRun(7, 12, connectionRun().id);
    expect(run.issues).toEqual([]);
    get.mockResolvedValueOnce({
      data: {
        counts: { pending: 0, retry: 0, paused: 0, in_flight: 0 },
        items: [],
        next_cursor: null,
      },
    });
    await listConnectionDeliveries(7, 12, { state: 'paused' });
    expect(get).toHaveBeenLastCalledWith(
      '/organizations/7/api-connections/12/deliveries/',
      { params: { state: 'paused' }, signal: undefined },
    );
  });
});
