// @vitest-environment jsdom
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useLeagueStore } from '~/store/leagueStore';

vi.mock('~/components/api/api', () => ({
  fetchLeague: vi.fn(async (pk: number) => ({ pk, organization: { pk: 8 } })),
}));

const { useLeague } = await import('../useLeague');

describe('useLeague', () => {
  it('stores the league before the first render that has it', async () => {
    const seenWithData: (number | undefined)[] = [];
    const { result } = renderHook(() => {
      const r = useLeague(3);
      if (r.league)
        seenWithData.push(useLeagueStore.getState().currentLeague?.pk);
      return r;
    });
    await waitFor(() => expect(result.current.league).not.toBeNull());
    expect(seenWithData[0]).toBe(3);
  });
});
