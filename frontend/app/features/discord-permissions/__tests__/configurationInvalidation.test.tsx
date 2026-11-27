// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { EventWritePayload } from '~/components/api/api';
import {
  useUpdateEventMutation,
  useUpdateEventRepeaterMutation,
  useUpdateOrgDefaultsMutation,
} from '~/hooks/useEvent';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { getEventPermissionChecks, postOrgPermissionChecks } from '../api';
import { usePermissionPreview, useSavedEventPermissions } from '../queries';
import { discordPermissionKeys } from '../queryKeys';
import type { PermissionChecksResponse } from '../schemas';

vi.mock('~/components/api/api', () => ({
  fetchCurrentUser: vi.fn(async () => ({})),
  updateEvent: vi.fn(async () => ({
    id: 9,
    organization: 7,
    discord_attendance_reminder_channel_id: 'B',
  })),
  updateEventRepeater: vi.fn(async () => ({})),
  updateOrgEventDefaults: vi.fn(async () => ({})),
}));
vi.mock('../api', () => ({
  getEventPermissionChecks: vi.fn(),
  postOrgPermissionChecks: vi.fn(),
}));
function response(channel: string): PermissionChecksResponse {
  return {
    guild_id: 'guild',
    checks: [
      {
        ...fixture.checks[1],
        key: 'attendance_reminder',
        destination: {
          ...fixture.checks[1].destination,
          channel_id: channel,
          name: channel,
        },
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60000).toISOString(),
      },
    ],
  } as PermissionChecksResponse;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
let client: QueryClient;
function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useUserStore.setState({ currentUser: { pk: 1 } as UserType });
  vi.mocked(getEventPermissionChecks).mockResolvedValue(response('A'));
});
afterEach(() => {
  cleanup();
  client.clear();
});

it.each(['ordinary', 'manual'] as const)(
  'event save clears same-guild grants and rejects a late %s response before publishing settings',
  async (kind) => {
    const { result } = renderHook(
      () => ({
        permissions: useSavedEventPermissions({
          eventId: 9,
          guildId: 'guild',
          enabled: true,
        }),
        mutation: useUpdateEventMutation(9),
      }),
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(result.current.permissions.state).toBe('ready'));
    const late = deferred<PermissionChecksResponse>();
    const fresh = deferred<PermissionChecksResponse>();
    vi.mocked(getEventPermissionChecks)
      .mockReturnValueOnce(late.promise)
      .mockReturnValue(fresh.promise);
    let pending!: Promise<unknown>;
    await act(async () => {
      pending =
        kind === 'manual'
          ? result.current.permissions.recheck()
          : result.current.permissions.refetch();
    });
    const signal = vi.mocked(getEventPermissionChecks).mock.calls[1][2]!;
    let saved!: Promise<unknown>;
    await act(async () => {
      saved = result.current.mutation.mutateAsync({
        discord_attendance_reminder_channel_id: 'B',
      } as EventWritePayload);
    });
    expect(signal.aborted).toBe(true);
    expect(result.current.permissions.results.size).toBe(0);
    expect(client.getQueryData(['event', 9])).toBeUndefined();
    await act(async () => {
      late.resolve(response('A'));
      await pending;
    });
    expect(result.current.permissions.results.size).toBe(0);
    await act(async () => {
      fresh.resolve(response('B'));
      await saved;
    });
    await waitFor(() =>
      expect(
        result.current.permissions.results.get('attendance_reminder')
          ?.destination.channel_id,
      ).toBe('B'),
    );
    expect(client.getQueryData(['event', 9])).toMatchObject({
      discord_attendance_reminder_channel_id: 'B',
    });
  },
);

it('event save also resets inactive previews across viewers and guilds without touching another event', async () => {
  const preview = discordPermissionKeys.draft(
    2,
    { kind: 'event', eventId: 9, guildId: 'other' },
    [],
  );
  const other = discordPermissionKeys.saved(1, 10, 'guild');
  client.setQueryData(preview, response('A'));
  client.setQueryData(other, response('A'));
  const { result } = renderHook(() => useUpdateEventMutation(9), {
    wrapper: Wrapper,
  });
  await act(async () => {
    await result.current.mutateAsync({} as EventWritePayload);
  });
  expect(client.getQueryData(preview)).toBeUndefined();
  expect(client.getQueryData(other)).toBeDefined();
});

it.each(['ordinary', 'manual'] as const)(
  'repeater cascade resets both mounted occurrences and their late %s replies without event-list metadata',
  async (kind) => {
    const { result } = renderHook(
      () => ({
        a: useSavedEventPermissions({
          eventId: 9,
          guildId: 'guild',
          enabled: true,
        }),
        b: useSavedEventPermissions({
          eventId: 10,
          guildId: 'guild',
          enabled: true,
        }),
        mutation: useUpdateEventRepeaterMutation(4),
      }),
      { wrapper: Wrapper },
    );
    await waitFor(() =>
      expect(
        result.current.a.state === 'ready' &&
          result.current.b.state === 'ready',
      ).toBe(true),
    );
    const late = deferred<PermissionChecksResponse>();
    const fresh = deferred<PermissionChecksResponse>();
    vi.mocked(getEventPermissionChecks)
      .mockReturnValueOnce(late.promise)
      .mockReturnValueOnce(late.promise)
      .mockReturnValue(fresh.promise);
    let pending!: Promise<unknown[]>;
    await act(async () => {
      pending = Promise.all(
        kind === 'manual'
          ? [result.current.a.recheck(), result.current.b.recheck()]
          : [result.current.a.refetch(), result.current.b.refetch()],
      );
    });
    const signals = vi
      .mocked(getEventPermissionChecks)
      .mock.calls.slice(2, 4)
      .map((call) => call[2]!);
    let saved!: Promise<unknown>;
    await act(async () => {
      saved = result.current.mutation.mutateAsync({});
    });
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    expect(
      client.getQueryData(discordPermissionKeys.saved(1, 9, 'guild')),
    ).toBeUndefined();
    expect(
      client.getQueryData(discordPermissionKeys.saved(1, 10, 'guild')),
    ).toBeUndefined();
    await waitFor(() =>
      expect(
        result.current.a.results.size + result.current.b.results.size,
      ).toBe(0),
    );
    await act(async () => {
      late.resolve(response('A'));
      await pending;
    });
    expect(result.current.a.results.size + result.current.b.results.size).toBe(
      0,
    );
    await act(async () => {
      fresh.resolve(response('B'));
      await saved;
    });
    await waitFor(() =>
      expect(
        [result.current.a, result.current.b].every(
          (q) =>
            q.results.get('attendance_reminder')?.destination.channel_id ===
            'B',
        ),
      ).toBe(true),
    );
  },
);

it('defaults save resets organization preview only, not existing occurrences', async () => {
  vi.mocked(postOrgPermissionChecks).mockResolvedValue(response('A'));
  const eventKey = discordPermissionKeys.saved(1, 9, 'guild');
  client.setQueryData(eventKey, response('A'));
  const { result } = renderHook(
    () => ({
      preview: usePermissionPreview({
        scope: { kind: 'org', orgId: 7, guildId: 'guild' },
        descriptors: [
          {
            key: 'attendance_reminder',
            action: 'attendance_reminder',
            channel_id: '123456789012345678',
            include_rsvp: false,
          },
        ],
        enabled: true,
      }),
      mutation: useUpdateOrgDefaultsMutation(7),
    }),
    { wrapper: Wrapper },
  );
  await waitFor(() => expect(result.current.preview.state).toBe('ready'));
  const fresh = deferred<PermissionChecksResponse>();
  vi.mocked(postOrgPermissionChecks).mockReturnValue(fresh.promise);
  let saved!: Promise<unknown>;
  await act(async () => {
    saved = result.current.mutation.mutateAsync({ id: 1, data: {} });
  });
  await waitFor(() => expect(result.current.preview.results.size).toBe(0));
  expect(client.getQueryData(eventKey)).toBeDefined();
  await act(async () => {
    fresh.resolve(response('B'));
    await saved;
  });
  await waitFor(() =>
    expect(
      result.current.preview.results.get('attendance_reminder')?.destination
        .channel_id,
    ).toBe('B'),
  );
});
