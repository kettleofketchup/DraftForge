// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LEAGUE_MMR_GAME } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { useUserStore } from '~/store/userStore';
import { resetGameType } from '~/test-utils/gameType';
import LeaguePage from '../league';

vi.mock('~/components/league', () => ({
  useLeague: () => ({
    league: null,
    isLoading: true,
    error: null,
    refetch: vi.fn(),
  }),
  LeagueTabs: () => null,
  EditLeagueModal: () => null,
}));
vi.mock('~/hooks/useMemberAccess', () => ({
  useMemberAccess: () => ({ canView: false, settled: false }),
}));
vi.mock('~/hooks/usePageNav', () => ({ usePageNav: () => undefined }));
vi.mock('~/hooks/usePermissions', () => ({
  useIsLeagueAdmin: () => false,
  useIsLeagueStaff: () => false,
}));

afterEach(() => {
  cleanup();
  resetGameType();
});

describe('LeaguePage game context', () => {
  it('puts the league MMR game in scope and clears it on leave', () => {
    useUserStore.setState({
      tournaments: [],
      getTournaments: vi.fn(async () => {}),
    } as never);
    const { unmount } = render(
      <MemoryRouter initialEntries={['/leagues/3']}>
        <Routes>
          <Route path="leagues/:leagueId/:tab?" element={<LeaguePage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(useGameTypeStore.getState().currentGameType).toBe(LEAGUE_MMR_GAME);
    unmount();
    expect(useGameTypeStore.getState().currentGameType).toBeNull();
  });
});
