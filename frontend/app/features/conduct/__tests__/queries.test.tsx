// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { conductKeys, standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { patchConductSettings } from '../api';
import { usePatchConductSettings } from '../queries';
import { conductSettings } from './fixtures';

vi.mock('../api', () => ({
  getConductSettings: vi.fn(),
  getMemberConduct: vi.fn(),
  patchConductSettings: vi.fn(),
}));

const ORG = 4;
const access = makeOrgFeatureAccess({ viewerPk: 9, canManageConduct: true });

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    settings: conductKeys.settings(ORG, 9),
    member: conductKeys.member(ORG, 9, 7, { limit: 50, offset: 0 }),
    board: standingKeys.leaderboard(ORG, 9, 'conduct', 'show_rate', 'all'),
  };
  client.setQueryData(keys.settings, conductSettings());
  client.setQueryData(keys.member, {});
  client.setQueryData(keys.board, {});
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => usePatchConductSettings(ORG, access), {
    wrapper,
  });
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { client, hook, keys, invalid };
}

afterEach(() => {
  vi.mocked(patchConductSettings).mockReset();
});

describe('usePatchConductSettings', () => {
  it('writes the saved settings and refreshes only dependent queries', async () => {
    const saved = conductSettings({ min_events: 5 });
    vi.mocked(patchConductSettings).mockResolvedValue(saved);
    const { client, hook, keys, invalid } = setup();
    await act(() => hook.result.current.mutateAsync({ min_events: 5 }));
    expect(client.getQueryData(keys.settings)).toEqual(saved);
    expect(invalid(keys.settings)).toBe(false);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.board)).toBe(true);
  });

  it('resyncs the settings after a failed save', async () => {
    vi.mocked(patchConductSettings).mockRejectedValue(new Error('400'));
    const { hook, keys, invalid } = setup();
    await act(async () => {
      await hook.result.current.mutateAsync({ min_events: 99 }).catch(() => {});
    });
    expect(invalid(keys.settings)).toBe(true);
  });
});
