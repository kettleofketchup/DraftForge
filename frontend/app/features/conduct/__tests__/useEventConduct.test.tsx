// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getForecast } from '../api';
import { useEventConduct } from '../useEventConduct';
import { forecast, forecastMember, MEMBER } from './fixtures';

vi.mock('../api', () => ({ getForecast: vi.fn() }));

const ORG = 4;
const access = makeOrgFeatureAccess({ settled: true, viewerPk: 9 });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => vi.clearAllMocks());

describe('useEventConduct', () => {
  it('looks members up by user pk once the forecast loads', async () => {
    const member = forecastMember({ show_rate: 0.5 });
    vi.mocked(getForecast).mockResolvedValue(
      forecast({ members: { [String(MEMBER.user_pk)]: member } }),
    );
    const { result } = renderHook(
      () =>
        useEventConduct(
          { id: 5, organization: ORG, user_can_manage: true },
          { features: ['conduct'] },
          access,
        ),
      { wrapper },
    );
    expect(result.current.enabled).toBe(true);
    await waitFor(() =>
      expect(result.current.memberFor(MEMBER.user_pk)).toEqual(member),
    );
    expect(result.current.memberFor(MEMBER.user_pk + 1)).toBeUndefined();
    expect(getForecast).toHaveBeenCalledWith(ORG, 5);
  });

  it('is disabled and fetches nothing for non-staff', () => {
    const { result } = renderHook(
      () =>
        useEventConduct(
          { id: 5, organization: ORG, user_can_manage: false },
          { features: ['conduct'] },
          access,
        ),
      { wrapper },
    );
    expect(result.current.enabled).toBe(false);
    expect(result.current.memberFor(MEMBER.user_pk)).toBeUndefined();
    expect(getForecast).not.toHaveBeenCalled();
  });
});
