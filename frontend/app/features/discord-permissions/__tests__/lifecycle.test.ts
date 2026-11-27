import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import {
  beginPermissionRefresh,
  invalidatePermissionChecks,
} from '../lifecycle';
import { discordPermissionKeys } from '../queryKeys';

const key = discordPermissionKeys.saved(1, 9, 'guild');
describe.each(['reset', 'remove'] as const)('%s cleanup', (mode) => {
  it('synchronously aborts manual refreshes and invalidates their generation', async () => {
    const client = new QueryClient();
    client.setQueryData(key, 'old');
    client.setQueryData(['other'], 'unrelated');
    const old = beginPermissionRefresh(client, key);
    const cleanup = invalidatePermissionChecks(
      client,
      { queryKey: discordPermissionKeys.all },
      mode,
    );
    expect(old.signal.aborted).toBe(true);
    expect(old.isCurrent()).toBe(false);
    await cleanup;
    expect(client.getQueryData(key)).toBeUndefined();
    expect(client.getQueryData(['other'])).toBe('unrelated');
    const next = beginPermissionRefresh(client, key);
    expect(next.isCurrent()).toBe(true);
    expect(old.isCurrent()).toBe(false);
    old.finish();
    next.finish();
    client.clear();
  });
});
it('cannot remove caches outside the permission namespace', async () => {
  const client = new QueryClient();
  client.setQueryData(['other'], 'unrelated');
  await invalidatePermissionChecks(client, {}, 'remove');
  expect(client.getQueryData(['other'])).toBe('unrelated');
  client.clear();
});
it('respects exact keys and query predicates when aborting refreshes', async () => {
  const client = new QueryClient();
  const first = beginPermissionRefresh(client, key);
  const otherKey = discordPermissionKeys.saved(2, 9, 'guild');
  const second = beginPermissionRefresh(client, otherKey);
  await invalidatePermissionChecks(
    client,
    { queryKey: key, exact: true },
    'remove',
  );
  expect(first.signal.aborted).toBe(true);
  expect(second.signal.aborted).toBe(false);
  first.finish();
  second.finish();
  client.clear();
});
