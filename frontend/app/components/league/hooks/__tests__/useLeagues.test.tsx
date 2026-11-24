// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createLeague, getLeagues, updateLeague } from '~/components/api/api';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { organizationsQueryKey } from '~/components/organization/hooks/useOrganizations';
import { useCreateLeagueMutation } from '../useCreateLeagueMutation';
import { useLeagues } from '../useLeagues';
import { useUpdateLeagueMutation } from '../useUpdateLeagueMutation';

vi.mock('~/components/api/api', () => ({
  getLeagues: vi.fn(),
  createLeague: vi.fn(),
  updateLeague: vi.fn(),
}));

function setup() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const league = (pk: number, name: string) =>
  ({ pk, name, organization: { pk: 1, name: 'DTX' } }) as never;

describe('useLeagues', () => {
  beforeEach(() => {
    vi.mocked(getLeagues).mockReset();
  });

  it('fetches the leagues of the given organization', async () => {
    const { wrapper } = setup();
    vi.mocked(getLeagues).mockResolvedValue([league(1, 'Main')]);

    const { result } = renderHook(() => useLeagues(1), { wrapper });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.leagues).toHaveLength(1));
    expect(getLeagues).toHaveBeenCalledWith(1);
  });

  it('shows a league created after the list loaded', async () => {
    const { qc, wrapper } = setup();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    vi.mocked(getLeagues).mockResolvedValueOnce([league(1, 'Main')]);

    const { result } = renderHook(
      () => ({ list: useLeagues(1), create: useCreateLeagueMutation(1) }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.list.leagues).toHaveLength(1));

    vi.mocked(createLeague).mockResolvedValue(league(2, 'Second'));
    vi.mocked(getLeagues).mockResolvedValueOnce([
      league(1, 'Main'),
      league(2, 'Second'),
    ]);
    await act(() =>
      result.current.create.mutateAsync({
        organization_id: 1,
        name: 'Second',
        description: '',
        rules: '',
      }),
    );

    await waitFor(() =>
      expect(result.current.list.leagues.map((l) => l.name)).toEqual([
        'Main',
        'Second',
      ]),
    );
    expect(createLeague).toHaveBeenCalledWith(
      expect.objectContaining({ organization_id: 1, name: 'Second' }),
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: organizationsQueryKey,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: organizationQueryKey(1),
    });
  });

  it('shows an edited league name in every loaded list', async () => {
    const { wrapper } = setup();
    vi.mocked(getLeagues).mockResolvedValue([league(1, 'Main')]);

    const { result } = renderHook(
      () => ({
        org: useLeagues(1),
        all: useLeagues(),
        update: useUpdateLeagueMutation(1),
      }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.org.leagues).toHaveLength(1);
      expect(result.current.all.leagues).toHaveLength(1);
    });

    vi.mocked(updateLeague).mockResolvedValue(league(1, 'Renamed'));
    vi.mocked(getLeagues).mockResolvedValue([league(1, 'Renamed')]);
    await act(() => result.current.update.mutateAsync({ name: 'Renamed' }));

    await waitFor(() => {
      expect(result.current.org.leagues[0].name).toBe('Renamed');
      expect(result.current.all.leagues[0].name).toBe('Renamed');
    });
  });
});
