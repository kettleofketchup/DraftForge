// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  renderHook,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { getEventPermissionChecks, postOrgPermissionChecks } from '../api';
import { invalidatePermissionChecks } from '../lifecycle';
import { usePermissionPreview, useSavedEventPermissions } from '../queries';
import { discordPermissionKeys, normalizeDescriptors } from '../queryKeys';
import type {
  CheckDescriptor,
  PermissionChecksResponse,
  PermissionScope,
} from '../schemas';

vi.mock('../api', () => ({
  postOrgPermissionChecks: vi.fn(),
  postEventPermissionChecks: vi.fn(),
  getEventPermissionChecks: vi.fn(),
}));
const scope: PermissionScope = { kind: 'org', orgId: 7, guildId: 'guild' };
const descriptors: CheckDescriptor[] = [
  {
    key: 'scheduled-create',
    action: 'scheduled_event_create',
    channel_id: null,
    include_rsvp: false,
  },
];
function response(): PermissionChecksResponse {
  return {
    guild_id: 'guild',
    checks: [
      {
        ...fixture.checks[1],
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      },
    ],
  } as PermissionChecksResponse;
}
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { resolve, reject, promise };
}
const clients: QueryClient[] = [];
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  clients.push(client);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}
beforeEach(() => {
  vi.resetAllMocks();
  useUserStore.setState({ currentUser: { pk: 1 } as UserType });
  vi.mocked(postOrgPermissionChecks).mockResolvedValue(response());
  vi.mocked(getEventPermissionChecks).mockResolvedValue(response());
});
afterEach(() => {
  cleanup();
  clients.forEach((c) => c.clear());
  clients.length = 0;
  vi.useRealTimers();
});
it('keys partition viewer, scope, guild, saved and draft, normalizing roles without mutation', () => {
  const key = discordPermissionKeys.draft(1, scope, descriptors);
  expect(key).not.toEqual(discordPermissionKeys.draft(2, scope, descriptors));
  expect(key).not.toEqual(
    discordPermissionKeys.draft(1, { ...scope, guildId: 'other' }, descriptors),
  );
  expect(key).not.toEqual(
    discordPermissionKeys.draft(
      1,
      { kind: 'event', eventId: 7, guildId: 'guild' },
      descriptors,
    ),
  );
  expect(key).not.toEqual(discordPermissionKeys.saved(1, 7, 'guild'));
  const a = [{ ...descriptors[0], role_ids: ['2', '1'] }];
  expect(discordPermissionKeys.draft(1, scope, a)).toEqual(
    discordPermissionKeys.draft(1, scope, [{ ...a[0], role_ids: ['1', '2'] }]),
  );
  expect(
    normalizeDescriptors([...a, { ...descriptors[0], key: 'a' }]).map(
      (d) => d.key,
    ),
  ).toEqual(['a', 'scheduled-create']);
  expect(a[0].role_ids).toEqual(['2', '1']);
});
it('drops old green immediately when the descriptor changes', async () => {
  const { wrapper } = setup();
  const { result, rerender } = renderHook(
    ({ d }) => usePermissionPreview({ scope, descriptors: d, enabled: true }),
    { wrapper, initialProps: { d: descriptors } },
  );
  await waitFor(() => expect(result.current.state).toBe('ready'));
  const next = deferred<PermissionChecksResponse>();
  vi.mocked(postOrgPermissionChecks).mockReturnValue(next.promise);
  rerender({ d: [{ ...descriptors[0], channel_id: '123456789012345678' }] });
  expect(result.current.results.size).toBe(0);
  expect(result.current.state).toBe('checking');
  await waitFor(() => expect(postOrgPermissionChecks).toHaveBeenCalledTimes(2));
  expect(result.current.results.size).toBe(0);
});
it('refetch failure never exposes cached green', async () => {
  const { wrapper } = setup();
  const { result } = renderHook(
    () => usePermissionPreview({ scope, descriptors, enabled: true }),
    { wrapper },
  );
  await waitFor(() => expect(result.current.state).toBe('ready'));
  vi.mocked(postOrgPermissionChecks).mockRejectedValue(new Error('offline'));
  await act(async () => {
    await result.current.refetch();
  });
  await waitFor(() => expect(result.current.state).toBe('error'));
  expect(result.current.results.size).toBe(0);
});
it('rechecks a whole batch once with refresh and an AbortSignal', async () => {
  const { wrapper } = setup();
  const { result } = renderHook(
    () => usePermissionPreview({ scope, descriptors, enabled: true }),
    { wrapper },
  );
  await waitFor(() => expect(result.current.state).toBe('ready'));
  await act(async () => {
    await result.current.recheck();
  });
  expect(postOrgPermissionChecks).toHaveBeenCalledTimes(2);
  expect(postOrgPermissionChecks).toHaveBeenLastCalledWith(
    7,
    { checks: normalizeDescriptors(descriptors), refresh: true },
    expect.any(AbortSignal),
  );
});
it('a manual failure clears green and a later ordinary response recovers', async () => {
  const { wrapper } = setup();
  const { result } = renderHook(
    () => usePermissionPreview({ scope, descriptors, enabled: true }),
    { wrapper },
  );
  await waitFor(() => expect(result.current.state).toBe('ready'));
  const error = new Error('refresh unavailable');
  vi.mocked(postOrgPermissionChecks).mockRejectedValueOnce(error);
  await act(async () => {
    await result.current.recheck();
  });
  expect(result.current.state).toBe('error');
  expect(result.current.results.size).toBe(0);
  await act(async () => {
    await result.current.refetch();
  });
  await waitFor(() => expect(result.current.state).toBe('ready'));
  expect(result.current.results.size).toBe(1);
});
it('does not request a missing org or viewer', async () => {
  const { wrapper } = setup();
  const { result } = renderHook(
    () =>
      usePermissionPreview({
        scope: { ...scope, orgId: 0 },
        descriptors,
        enabled: true,
      }),
    { wrapper },
  );
  expect(result.current.state).toBe('idle');
  expect(postOrgPermissionChecks).not.toHaveBeenCalled();
});
it('expires a cached result before the next poll', async () => {
  vi.useFakeTimers();
  const data = response();
  data.checks[0].expires_at = new Date(Date.now() + 2000).toISOString();
  const { client, wrapper } = setup();
  client.setQueryData(discordPermissionKeys.saved(1, 9, 'guild'), data);
  vi.mocked(getEventPermissionChecks).mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(
    () =>
      useSavedEventPermissions({ eventId: 9, guildId: 'guild', enabled: true }),
    { wrapper },
  );
  expect(result.current.results.size).toBe(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2001);
  });
  expect(result.current.results.get('scheduled-create')?.status).toBe(
    'unknown',
  );
  expect(result.current.results.get('scheduled-create')?.expires_at).toBe(
    data.checks[0].expires_at,
  );
  expect(result.current.results.get('scheduled-create')?.granted).toEqual(
    data.checks[0].granted,
  );
});
it('reassesses expiry on tab return even when timers and the transport have not fired', () => {
  vi.useFakeTimers();
  const data = response();
  data.checks[0].expires_at = new Date(Date.now() + 2000).toISOString();
  const { client, wrapper } = setup();
  client.setQueryData(discordPermissionKeys.saved(1, 9, 'guild'), data);
  vi.mocked(getEventPermissionChecks).mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(
    () =>
      useSavedEventPermissions({ eventId: 9, guildId: 'guild', enabled: true }),
    { wrapper },
  );
  expect(result.current.results.get('scheduled-create')?.status).toBe(
    'verified',
  );
  vi.setSystemTime(Date.now() + 3000);
  fireEvent(window, new Event('focus'));
  expect(result.current.results.get('scheduled-create')?.status).toBe(
    'unknown',
  );
  expect(result.current.results.get('scheduled-create')?.expired).toBe(true);
});
it('never exposes an already-expired cached snapshot as verified at mount', () => {
  const data = response();
  data.checks[0].expires_at = new Date(Date.now() - 1).toISOString();
  const { client, wrapper } = setup();
  client.setQueryData(discordPermissionKeys.saved(1, 9, 'guild'), data);
  vi.mocked(getEventPermissionChecks).mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(
    () =>
      useSavedEventPermissions({ eventId: 9, guildId: 'guild', enabled: true }),
    { wrapper },
  );
  expect(result.current.results.get('scheduled-create')?.status).toBe(
    'unknown',
  );
});
describe.each(['reset', 'remove'] as const)('%s lifecycle', (mode) => {
  it('ignores an aborted manual reply even when transport ignores abort', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(
      () => usePermissionPreview({ scope, descriptors, enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.state).toBe('ready'));
    const late = deferred<PermissionChecksResponse>();
    const fresh = deferred<PermissionChecksResponse>();
    vi.mocked(postOrgPermissionChecks)
      .mockReturnValueOnce(late.promise)
      .mockReturnValue(fresh.promise);
    let recheck!: Promise<void>;
    await act(async () => {
      recheck = result.current.recheck();
    });
    const signal = vi.mocked(postOrgPermissionChecks).mock.calls[1][2]!;
    await act(async () => {
      const reset = invalidatePermissionChecks(
        client,
        { queryKey: discordPermissionKeys.all },
        mode,
      );
      if (mode === 'remove') await reset;
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      late.resolve(response());
      await recheck;
    });
    const key = discordPermissionKeys.draft(1, scope, descriptors);
    expect(client.getQueryData(key)).toBeUndefined();
    expect(result.current.isRechecking).toBe(false);
    if (mode === 'reset') {
      await act(async () => {
        fresh.resolve(response());
      });
      await waitFor(() => expect(result.current.state).toBe('ready'));
    }
  });
  it('ignores a cancelled ordinary fetch that resolves late', async () => {
    const late = deferred<PermissionChecksResponse>();
    const fresh = deferred<PermissionChecksResponse>();
    vi.mocked(postOrgPermissionChecks)
      .mockReturnValueOnce(late.promise)
      .mockReturnValue(fresh.promise);
    const { client, wrapper } = setup();
    renderHook(
      () => usePermissionPreview({ scope, descriptors, enabled: true }),
      { wrapper },
    );
    await waitFor(() =>
      expect(postOrgPermissionChecks).toHaveBeenCalledTimes(1),
    );
    const signal = vi.mocked(postOrgPermissionChecks).mock.calls[0][2]!;
    await act(async () => {
      void invalidatePermissionChecks(
        client,
        { queryKey: discordPermissionKeys.all },
        mode,
      );
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      late.resolve(response());
    });
    expect(
      client.getQueryData(discordPermissionKeys.draft(1, scope, descriptors)),
    ).toBeUndefined();
  });
});
it.each(['draft', 'unmount', 'viewer'] as const)(
  'aborts manual recheck on %s changes without leaking state',
  async (change) => {
    const { client, wrapper } = setup();
    const { result, rerender, unmount } = renderHook(
      ({ d }) => usePermissionPreview({ scope, descriptors: d, enabled: true }),
      { wrapper, initialProps: { d: descriptors } },
    );
    await waitFor(() => expect(result.current.state).toBe('ready'));
    const late = deferred<PermissionChecksResponse>();
    vi.mocked(postOrgPermissionChecks).mockReturnValue(late.promise);
    let recheck!: Promise<void>;
    await act(async () => {
      recheck = result.current.recheck();
    });
    const signal = vi.mocked(postOrgPermissionChecks).mock.calls[1][2]!;
    if (change === 'unmount') unmount();
    else if (change === 'draft')
      rerender({ d: [{ ...descriptors[0], key: 'other' }] });
    else {
      act(() => {
        useUserStore.setState({ currentUser: null as unknown as UserType });
      });
      await act(async () => {
        await invalidatePermissionChecks(client, {}, 'remove');
      });
      act(() => {
        useUserStore.setState({ currentUser: { pk: 2 } as UserType });
      });
    }
    expect(signal.aborted).toBe(true);
    await act(async () => {
      late.reject(new Error('late'));
      await recheck;
    });
    if (change !== 'unmount') {
      expect(result.current.error).toBeNull();
      expect(result.current.isRechecking).toBe(false);
      expect(result.current.results.size).toBe(0);
    }
  },
);
