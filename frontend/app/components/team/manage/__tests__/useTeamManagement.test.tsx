// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import type { TournamentType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { useUserStore } from '~/store/userStore';
import { managedTeam, people } from './fixtures';

const api = vi.hoisted(() => ({
  fetchManagedTeam: vi.fn(),
  runTeamAction: vi.fn(),
  fetchTeamHistory: vi.fn(),
}));
const orgApi = vi.hoisted(() => ({ fetchOrganization: vi.fn() }));
const logSpy = vi.hoisted(() => ({
  info: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
  debug: vi.fn(),
}));
const toastSpy = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock('~/components/api/teamManagementAPI', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('~/components/api/teamManagementAPI')
  >()),
  ...api,
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...orgApi,
}));
vi.mock('~/lib/logger', () => ({ getLogger: () => logSpy }));
vi.mock('sonner', () => ({ toast: toastSpy }));

import {
  rosterSignature,
  teamManageKeys,
  useCanEditCurrentTournament,
  useInvalidateOnRosterChange,
  useManagedTeam,
  useTeamActionMutation,
  useTeamHistory,
} from '../useTeamManagement';

const TEAM_ID = managedTeam.pk;
const TOURNAMENT_PK = 7;
const VIEWER_PK = 501;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

function setViewer(pk: number | null): void {
  useUserStore.setState({
    currentUser: new User(
      (pk == null ? {} : { pk, username: 'viewer' }) as UserType,
    ),
  });
}

function setTournament(league: unknown, organizationPk: number | null): void {
  useUserStore.setState({
    tournament: {
      pk: TOURNAMENT_PK,
      league,
      organization_pk: organizationPk,
    } as unknown as TournamentType,
  });
}

const initialState = useUserStore.getState();

afterEach(() => {
  useUserStore.setState(initialState, true);
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('teamManageKeys', () => {
  it('nests managed and history under the team key', () => {
    expect(teamManageKeys.all(3)).toEqual(['team', 3]);
    expect(teamManageKeys.managed(3)).toEqual(['team', 3, 'managed']);
    expect(teamManageKeys.history(3)).toEqual(['team', 3, 'history']);
    expect(teamManageKeys.history(3, 2)).toEqual(['team', 3, 'history', 2]);
  });
});

describe('useManagedTeam', () => {
  it('sends no request for a null team id', async () => {
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useManagedTeam(null, { enabled: true }),
      { wrapper },
    );
    await Promise.resolve();
    expect(api.fetchManagedTeam).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('sends no request while disabled', async () => {
    const { wrapper } = setup();
    renderHook(() => useManagedTeam(TEAM_ID, { enabled: false }), {
      wrapper,
    });
    await Promise.resolve();
    expect(api.fetchManagedTeam).not.toHaveBeenCalled();
  });

  it('fetches the managed team when enabled with an id', async () => {
    api.fetchManagedTeam.mockResolvedValue(managedTeam);
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useManagedTeam(TEAM_ID, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toEqual(managedTeam));
    expect(api.fetchManagedTeam).toHaveBeenCalledWith(TEAM_ID);
  });
});

describe('useTeamHistory', () => {
  it('requests the page with a page size of 25', async () => {
    api.fetchTeamHistory.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    const { wrapper } = setup();
    const { result } = renderHook(() => useTeamHistory(TEAM_ID, 2), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.fetchTeamHistory).toHaveBeenCalledWith(TEAM_ID, 2, 25);
  });

  const page = (count: number) => ({
    count,
    next: null,
    previous: null,
    results: [],
  });

  it('keeps the previous page while paging within one team', async () => {
    api.fetchTeamHistory.mockResolvedValueOnce(page(30));
    api.fetchTeamHistory.mockReturnValueOnce(new Promise(() => undefined));
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ p }: { p: number }) => useTeamHistory(TEAM_ID, p),
      { wrapper, initialProps: { p: 1 } },
    );
    await waitFor(() => expect(result.current.data?.count).toBe(30));
    rerender({ p: 2 });
    expect(result.current.data?.count).toBe(30);
  });

  it('drops the previous team history when the team changes', async () => {
    api.fetchTeamHistory.mockResolvedValueOnce(page(30));
    api.fetchTeamHistory.mockReturnValueOnce(new Promise(() => undefined));
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ id }: { id: number }) => useTeamHistory(id, 1),
      { wrapper, initialProps: { id: TEAM_ID } },
    );
    await waitFor(() => expect(result.current.data?.count).toBe(30));
    rerender({ id: TEAM_ID + 1 });
    expect(result.current.data).toBeUndefined();
  });
});

describe('useTeamActionMutation', () => {
  const action = { kind: 'set_captain' as const, user: people.member };
  const body = { reason: 'swap', acknowledged_codes: [] };

  it('writes the returned team and invalidates the tournament and history', async () => {
    const updated = { ...managedTeam, name: 'Renamed' };
    api.runTeamAction.mockResolvedValue(updated);
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(
      () => useTeamActionMutation(TEAM_ID, TOURNAMENT_PK),
      { wrapper },
    );

    await act(() => result.current.mutateAsync({ action, body }));

    expect(api.runTeamAction).toHaveBeenCalledWith(TEAM_ID, action, body);
    expect(client.getQueryData(teamManageKeys.managed(TEAM_ID))).toEqual(
      updated,
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ['tournament', TOURNAMENT_PK],
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: teamManageKeys.history(TEAM_ID),
    });
    expect(logSpy.info).toHaveBeenCalledWith('Team action succeeded', {
      teamId: TEAM_ID,
      kind: 'set_captain',
    });
  });

  it('regression pin: mutation has no onError, a rejection triggers no toast or log error', async () => {
    api.runTeamAction.mockRejectedValue(new Error('409'));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useTeamActionMutation(TEAM_ID, TOURNAMENT_PK),
      { wrapper },
    );

    await act(async () => {
      await expect(
        result.current.mutateAsync({ action, body }),
      ).rejects.toThrow('409');
    });

    expect(toastSpy.error).not.toHaveBeenCalled();
    expect(logSpy.error).not.toHaveBeenCalled();
    expect(logSpy.info).not.toHaveBeenCalled();
  });
});

describe('rosterSignature', () => {
  const base = {
    captain: { pk: 1 },
    deputy_captain: { pk: 2 },
    members: [{ pk: 1 }, { pk: 2 }, { pk: 3 }],
    dropin_members: [{ pk: 9 }],
    left_members: [],
  };

  it('ignores member order', () => {
    expect(
      rosterSignature({
        ...base,
        members: [{ pk: 3 }, { pk: 1 }, { pk: 2 }],
      }),
    ).toBe(rosterSignature(base));
  });

  it('treats bare pks like hydrated users', () => {
    expect(
      rosterSignature({
        captain: 1,
        deputy_captain: 2,
        members: [3, 2, 1],
        dropin_members: [9],
        left_members: [],
      }),
    ).toBe(rosterSignature(base));
  });

  it('changes when the deputy changes', () => {
    expect(rosterSignature({ ...base, deputy_captain: { pk: 3 } })).not.toBe(
      rosterSignature(base),
    );
    expect(rosterSignature({ ...base, deputy_captain: null })).not.toBe(
      rosterSignature(base),
    );
  });

  it('distinguishes a stand-in from a dropout', () => {
    expect(
      rosterSignature({
        ...base,
        dropin_members: [],
        left_members: [{ pk: 9 }],
      }),
    ).not.toBe(rosterSignature(base));
  });
});

describe('useInvalidateOnRosterChange', () => {
  it('invalidates once after a change and not on mount', () => {
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { rerender } = renderHook(
      ({ sig }: { sig: string }) => useInvalidateOnRosterChange(TEAM_ID, sig),
      { wrapper, initialProps: { sig: 'a' } },
    );
    expect(invalidate).not.toHaveBeenCalled();

    rerender({ sig: 'a' });
    expect(invalidate).not.toHaveBeenCalled();

    rerender({ sig: 'b' });
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: teamManageKeys.all(TEAM_ID),
    });

    rerender({ sig: 'b' });
    expect(invalidate).toHaveBeenCalledTimes(1);
  });

  it('does nothing for a null team id', () => {
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { rerender } = renderHook(
      ({ sig }: { sig: string }) => useInvalidateOnRosterChange(null, sig),
      { wrapper, initialProps: { sig: 'a' } },
    );
    rerender({ sig: 'b' });
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe('useCanEditCurrentTournament', () => {
  const ORG_PK = 40;

  function render() {
    const { wrapper } = setup();
    return renderHook(() => useCanEditCurrentTournament(), { wrapper });
  }

  it('is true for league staff who are not org staff', () => {
    setViewer(VIEWER_PK);
    setTournament({ pk: 3, staff_ids: [VIEWER_PK], admin_ids: [] }, null);
    expect(render().result.current).toBe(true);
  });

  it('is true for a league admin', () => {
    setViewer(VIEWER_PK);
    setTournament({ pk: 3, staff_ids: [], admin_ids: [VIEWER_PK] }, null);
    expect(render().result.current).toBe(true);
  });

  it('is true for org staff, reading the org without writing orgStore', async () => {
    setViewer(VIEWER_PK);
    setTournament({ pk: 3, staff_ids: [], admin_ids: [] }, ORG_PK);
    orgApi.fetchOrganization.mockResolvedValue({
      pk: ORG_PK,
      name: 'Org',
      admin_ids: [],
      staff_ids: [VIEWER_PK],
    } as unknown as OrganizationType);
    const { useOrgStore } = await import('~/store/orgStore');
    const setCurrentOrg = vi.spyOn(useOrgStore.getState(), 'setCurrentOrg');

    const { result } = render();

    await waitFor(() => expect(result.current).toBe(true));
    expect(orgApi.fetchOrganization).toHaveBeenCalledWith(ORG_PK);
    expect(setCurrentOrg).not.toHaveBeenCalled();
  });

  it('is false for a plain user', async () => {
    setViewer(VIEWER_PK);
    setTournament({ pk: 3, staff_ids: [1], admin_ids: [2] }, ORG_PK);
    orgApi.fetchOrganization.mockResolvedValue({
      pk: ORG_PK,
      name: 'Org',
      admin_ids: [],
      staff_ids: [3],
    } as unknown as OrganizationType);

    const { result } = render();

    await waitFor(() =>
      expect(orgApi.fetchOrganization).toHaveBeenCalledWith(ORG_PK),
    );
    expect(result.current).toBe(false);
  });

  it('is false for the default empty user', () => {
    setViewer(null);
    setTournament({ pk: 3, staff_ids: [VIEWER_PK], admin_ids: [] }, null);
    expect(render().result.current).toBe(false);
  });
});
