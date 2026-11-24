// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useDeleteLeagueMutation } from '../useDeleteLeagueMutation';

vi.mock('~/components/api/api', () => ({
  deleteLeague: vi.fn().mockResolvedValue(undefined),
}));

describe('useDeleteLeagueMutation', () => {
  it('refreshes league lists and the org league counts', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useDeleteLeagueMutation(7, 3), {
      wrapper,
    });

    await act(() => result.current.mutateAsync());

    const keys = spy.mock.calls.map(([f]) => f?.queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        ['leagues'],
        ['organizations'],
        ['organization', 3],
      ]),
    );
  });
});
