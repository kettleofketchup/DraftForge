// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { discordKeys } from '../queryKeys';
import { useOrgDiscordResolver } from '../useOrgDiscordResolver';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { get } }));

const ROLES = {
  roles: [
    {
      id: '11',
      name: 'Inhouse',
      color: 0xff0000,
      mentionable: true,
      position: 2,
    },
    { id: '12', name: 'Dota', color: 0, mentionable: true, position: 1 },
  ],
};
const CHANNELS = {
  channels: [{ id: '21', name: 'general', type: 0, type_label: 'text' }],
};

function respond(roles: unknown, channels: unknown) {
  get.mockImplementation((url: string) => {
    if (url.includes('/roles/'))
      return roles instanceof Error
        ? Promise.reject(roles)
        : Promise.resolve({ data: roles });
    return channels instanceof Error
      ? Promise.reject(channels)
      : Promise.resolve({ data: channels });
  });
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  get.mockReset();
});

describe('discordKeys', () => {
  it('scopes roles and channels by org', () => {
    expect(discordKeys.roles(7)).toEqual(['discord', 'roles', 7]);
    expect(discordKeys.channels(7)).toEqual(['discord', 'channels', 7]);
  });
});

describe('useOrgDiscordResolver', () => {
  it('maps roles and channels to names', async () => {
    respond(ROLES, CHANNELS);
    const { result } = renderHook(
      () => useOrgDiscordResolver(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() =>
      expect(result.current).toEqual({
        roles: {
          '11': { name: 'Inhouse', color: 0xff0000 },
          '12': { name: 'Dota', color: 0 },
        },
        channels: { '21': 'general' },
      }),
    );
    expect(get).toHaveBeenCalledWith('/discord/organizations/5/roles/');
    expect(get).toHaveBeenCalledWith('/discord/organizations/5/channels/');
  });

  it('yields an empty resolver when both fetches fail', async () => {
    respond(new Error('boom'), new Error('boom'));
    const { result } = renderHook(
      () => useOrgDiscordResolver(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await new Promise((r) => setTimeout(r, 0));
    expect(result.current).toEqual({});
  });

  it('drops a malformed roles payload and keeps channels', async () => {
    respond({ roles: [{ id: 11, name: null }] }, CHANNELS);
    const { result } = renderHook(
      () => useOrgDiscordResolver(5, { enabled: true }),
      { wrapper },
    );
    await waitFor(() =>
      expect(result.current).toEqual({ channels: { '21': 'general' } }),
    );
    expect(result.current.roles).toBeUndefined();
  });

  it('does not fetch while disabled or without an org', async () => {
    respond(ROLES, CHANNELS);
    const { result } = renderHook(
      ({ orgId, enabled }: { orgId: number | undefined; enabled: boolean }) =>
        useOrgDiscordResolver(orgId, { enabled }),
      { wrapper, initialProps: { orgId: 5, enabled: false } },
    );
    const { result: noOrg } = renderHook(
      () => useOrgDiscordResolver(undefined, { enabled: true }),
      { wrapper },
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(get).not.toHaveBeenCalled();
    expect(result.current).toEqual({});
    expect(noOrg.current).toEqual({});
  });
});
