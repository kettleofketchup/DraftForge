// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { conductKeys, standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getForecast, patchConductSettings, putAttendance } from '../api';
import {
  useForecast,
  usePatchConductSettings,
  usePutAttendance,
} from '../queries';
import { attendance, conductSettings, forecast } from './fixtures';

vi.mock('../api', () => ({
  getAttendance: vi.fn(),
  getConductSettings: vi.fn(),
  getForecast: vi.fn(),
  getMemberConduct: vi.fn(),
  patchConductSettings: vi.fn(),
  putAttendance: vi.fn(),
}));

const ORG = 4;
const EVENT = 5;
const access = makeOrgFeatureAccess({ viewerPk: 9, canManageConduct: true });

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    settings: conductKeys.settings(ORG, 9),
    member: conductKeys.member(ORG, 9, 7, { limit: 50, offset: 0 }),
    board: standingKeys.leaderboard(ORG, 9, 'conduct', 'show_rate', 'all'),
    forecast: conductKeys.forecast(ORG, 9, EVENT),
  };
  client.setQueryData(keys.settings, conductSettings());
  client.setQueryData(keys.member, {});
  client.setQueryData(keys.board, {});
  client.setQueryData(keys.forecast, {});
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
  vi.mocked(putAttendance).mockReset();
  vi.mocked(getForecast).mockReset();
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

  it('refreshes the event forecast but keeps settings', async () => {
    vi.mocked(patchConductSettings).mockResolvedValue(conductSettings());
    const { hook, keys, invalid } = setup();
    await act(() => hook.result.current.mutateAsync({ block_enabled: true }));
    expect(invalid(keys.forecast)).toBe(true);
    expect(invalid(keys.settings)).toBe(false);
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

function makeClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe('useForecast', () => {
  it('does not fetch when not enabled or not settled', async () => {
    const { wrapper } = makeClient();
    renderHook(
      () =>
        useForecast(ORG, makeOrgFeatureAccess({ settled: true }), EVENT, false),
      { wrapper },
    );
    renderHook(
      () =>
        useForecast(ORG, makeOrgFeatureAccess({ settled: false }), EVENT, true),
      { wrapper },
    );
    await Promise.resolve();
    expect(getForecast).not.toHaveBeenCalled();
  });

  it('fetches when enabled and settled', async () => {
    vi.mocked(getForecast).mockResolvedValue(forecast());
    const { wrapper } = makeClient();
    const hook = renderHook(
      () =>
        useForecast(
          ORG,
          makeOrgFeatureAccess({ settled: true, viewerPk: 9 }),
          EVENT,
          true,
        ),
      { wrapper },
    );
    await waitFor(() =>
      expect(hook.result.current.data?.seat_holders).toBe(30),
    );
    expect(getForecast).toHaveBeenCalledWith(ORG, EVENT);
  });
});

describe('usePutAttendance', () => {
  const putAccess = makeOrgFeatureAccess({ settled: true, viewerPk: 9 });

  function setupPut() {
    const { client, wrapper } = makeClient();
    const keys = {
      attendance: conductKeys.attendance(ORG, 9, EVENT),
      forecast: conductKeys.forecast(ORG, 9, EVENT),
      member: conductKeys.member(ORG, 9, 7, { limit: 50, offset: 0 }),
      conductBoard: standingKeys.leaderboard(
        ORG,
        9,
        'conduct',
        'show_rate',
        'current',
      ),
      contributionBoard: standingKeys.leaderboard(
        ORG,
        9,
        'contribution',
        'points',
        'all',
      ),
    };
    for (const key of Object.values(keys)) client.setQueryData(key, {});
    client.setQueryData(keys.attendance, attendance());
    const hook = renderHook(() => usePutAttendance(ORG, putAccess, EVENT), {
      wrapper,
    });
    const invalid = (key: readonly unknown[]) =>
      client.getQueryState(key)?.isInvalidated ?? false;
    return { client, hook, keys, invalid };
  }

  const BODY = {
    changes: [{ org_user_pk: 7, outcome: 'no_show' as const }],
    reason: 'Did not show',
  };

  it('writes the response and refreshes forecast, member and conduct board', async () => {
    const saved = attendance({ editable: false });
    vi.mocked(putAttendance).mockResolvedValue(saved);
    const { client, hook, keys, invalid } = setupPut();
    await act(() => hook.result.current.mutateAsync(BODY));
    expect(putAttendance).toHaveBeenCalledWith(ORG, EVENT, BODY);
    expect(client.getQueryData(keys.attendance)).toEqual(saved);
    expect(invalid(keys.attendance)).toBe(false);
    expect(invalid(keys.forecast)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.conductBoard)).toBe(true);
    expect(invalid(keys.contributionBoard)).toBe(false);
  });

  it('invalidates attendance too after a failed save', async () => {
    vi.mocked(putAttendance).mockRejectedValue(new Error('400'));
    const { hook, keys, invalid } = setupPut();
    await act(async () => {
      await hook.result.current.mutateAsync(BODY).catch(() => {});
    });
    expect(invalid(keys.attendance)).toBe(true);
    expect(invalid(keys.forecast)).toBe(true);
  });
});
