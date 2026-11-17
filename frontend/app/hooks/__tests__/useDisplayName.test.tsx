// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { DisplayOrgProvider } from '~/lib/displayOrgContext';
import { useUserCacheStore } from '~/store/userCacheStore';

import { useDisplayName } from '../useDisplayName';
import { useDisplayOrgId } from '../useDisplayOrgId';

const rawDragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};

const upsertDragonNick = (orgId: number) =>
  useUserCacheStore
    .getState()
    .upsert({ ...rawDragon, guildNickname: 'DragonClaw' } as never, { orgId });

const withOrg =
  (orgId: number | null | undefined) =>
  ({ children }: { children: ReactNode }) => (
    <DisplayOrgProvider orgId={orgId}>{children}</DisplayOrgProvider>
  );

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('useDisplayOrgId', () => {
  it('is null without a provider', () => {
    const { result } = renderHook(() => useDisplayOrgId());
    expect(result.current).toBeNull();
  });

  it('returns the provider org', () => {
    const { result } = renderHook(() => useDisplayOrgId(), {
      wrapper: withOrg(7),
    });
    expect(result.current).toBe(7);
  });

  it('treats an undefined provider org as global', () => {
    const { result } = renderHook(() => useDisplayOrgId(), {
      wrapper: withOrg(undefined),
    });
    expect(result.current).toBeNull();
  });
});

describe('useDisplayName', () => {
  it('updates a raw object when its org nickname arrives in the store', () => {
    const { result } = renderHook(() => useDisplayName(rawDragon, 7));
    expect(result.current).toBe('GwaihirTheWindlord');
    act(() => upsertDragonNick(7));
    expect(result.current).toBe('DragonClaw');
  });

  it('does not re-render on an unrelated upsert', () => {
    let renders = 0;
    renderHook(() => {
      renders += 1;
      return useDisplayName(rawDragon, 7);
    });
    const before = renders;
    act(() =>
      useUserCacheStore
        .getState()
        .upsert({ pk: 2, username: 'other' } as never, { orgId: 7 }),
    );
    expect(renders).toBe(before);
  });

  it('resolves by pk from the store', () => {
    upsertDragonNick(7);
    const { result: global } = renderHook(() => useDisplayName(1, null));
    expect(global.current).toBe('GwaihirTheWindlord');
    const { result: org } = renderHook(() => useDisplayName(1, 7));
    expect(org.current).toBe('DragonClaw');
  });

  it('falls back for an unknown pk and empty input', () => {
    expect(renderHook(() => useDisplayName(99, null)).result.current).toBe(
      'User 99',
    );
    expect(renderHook(() => useDisplayName(null, 7)).result.current).toBe('?');
  });

  it('never lets a partial store entry shadow raw fields', () => {
    act(() =>
      useUserCacheStore
        .getState()
        .upsert({ pk: 1, username: 'stale' } as never),
    );
    const { result } = renderHook(() => useDisplayName(rawDragon, null));
    expect(result.current).toBe('GwaihirTheWindlord');
  });

  it('shows no org-7 nickname under an org-8 provider', () => {
    upsertDragonNick(7);
    const { result } = renderHook(
      () => useDisplayName(rawDragon, useDisplayOrgId()),
      { wrapper: withOrg(8) },
    );
    expect(result.current).toBe('GwaihirTheWindlord');
  });

  it('uses the provider org when the caller passes it', () => {
    upsertDragonNick(7);
    const { result } = renderHook(
      () => useDisplayName(rawDragon, useDisplayOrgId()),
      { wrapper: withOrg(7) },
    );
    expect(result.current).toBe('DragonClaw');
  });

  it('resolves a Discord guild member and truncates', () => {
    const member = {
      nick: 'ServerNick',
      user: { username: 'u', global_name: 'G' },
    };
    const { result } = renderHook(() =>
      useDisplayName(member, 7, { maxLength: 6 }),
    );
    expect(result.current).toBe('Server…');
  });
});
