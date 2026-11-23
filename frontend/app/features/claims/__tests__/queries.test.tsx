// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getClaimRequests } from '../api';
import { useInvalidateClaims, usePendingClaimsCount } from '../queries';
import type { ProfileClaimRequest } from '../schemas';

vi.mock('../api', () => ({ getClaimRequests: vi.fn() }));

const pending = (id: number) =>
  ({ id, status: 'pending' }) as ProfileClaimRequest;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.mocked(getClaimRequests).mockReset();
});

describe('usePendingClaimsCount', () => {
  it('counts pending claims for the org', async () => {
    vi.mocked(getClaimRequests).mockResolvedValue([pending(1), pending(2)]);
    const { result } = renderHook(() => usePendingClaimsCount(7, true), {
      wrapper,
    });
    await waitFor(() => expect(result.current).toBe(2));
    expect(getClaimRequests).toHaveBeenCalledWith({
      organizationId: 7,
      status: 'pending',
    });
  });

  it('does not fetch when disabled or without an org', () => {
    renderHook(() => usePendingClaimsCount(7, false), { wrapper });
    renderHook(() => usePendingClaimsCount(undefined, true), { wrapper });
    expect(getClaimRequests).not.toHaveBeenCalled();
  });

  it('refetches after the claims are invalidated', async () => {
    vi.mocked(getClaimRequests).mockResolvedValue([pending(1), pending(2)]);
    const { result } = renderHook(
      () => ({
        count: usePendingClaimsCount(7, true),
        invalidate: useInvalidateClaims(7),
      }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.count).toBe(2));
    vi.mocked(getClaimRequests).mockResolvedValue([pending(2)]);
    await act(() => result.current.invalidate());
    await waitFor(() => expect(result.current.count).toBe(1));
  });
});
