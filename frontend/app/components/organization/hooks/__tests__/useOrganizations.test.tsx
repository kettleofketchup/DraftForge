// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { getOrganizations } from '~/components/api/api';
import { useOrganizations } from '../useOrganizations';

vi.mock('~/components/api/api', () => ({ getOrganizations: vi.fn() }));

describe('useOrganizations', () => {
  it('refetch picks up an organization created after the first load', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    vi.mocked(getOrganizations).mockResolvedValueOnce([
      { pk: 1, name: 'DTX' } as never,
    ]);

    const { result } = renderHook(() => useOrganizations(), { wrapper });
    await waitFor(() => expect(result.current.organizations).toHaveLength(1));

    vi.mocked(getOrganizations).mockResolvedValueOnce([
      { pk: 1, name: 'DTX' } as never,
      { pk: 2, name: 'New Org' } as never,
    ]);
    await act(() => result.current.refetch());

    expect(getOrganizations).toHaveBeenCalledTimes(2);
    await waitFor(() =>
      expect(result.current.organizations.map((o) => o.name)).toEqual([
        'DTX',
        'New Org',
      ]),
    );
  });
});
