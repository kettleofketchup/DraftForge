// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react';
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
  type NavigateFunction,
} from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { resetGameType } from '~/test-utils/gameType';
import TournamentDetailPage from '../TournamentDetailPage';

const tournaments = vi.hoisted(() => ({
  byPk: {} as Record<number, { pk: number; name: string; game_type?: number }>,
}));

vi.mock('~/hooks/useTournament', () => ({
  useTournament: (pk: number | null) => ({
    data: pk == null ? undefined : tournaments.byPk[pk],
    isLoading: false,
    error: null,
  }),
}));
vi.mock('~/hooks/useTournamentSocket', () => ({
  useTournamentSocket: () => undefined,
}));
vi.mock('../tabs/TournamentTabs', () => ({ default: () => null }));

const current = () => useGameTypeStore.getState().currentGameType;

let navigate: NavigateFunction;
function CaptureNavigate() {
  navigate = useNavigate();
  return null;
}

function renderAt(pk: number) {
  return render(
    <MemoryRouter initialEntries={[`/tournament/${pk}`]}>
      <CaptureNavigate />
      <Routes>
        <Route path="tournament/:pk/*" element={<TournamentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  resetGameType();
  tournaments.byPk = {};
});

describe('TournamentDetailPage game context', () => {
  it('puts the tournament game in scope and clears it on leave', () => {
    tournaments.byPk[1] = {
      pk: 1,
      name: 'Deadlock Cup',
      game_type: GAME_TYPE.DEADLOCK,
    };
    const { unmount } = renderAt(1);
    expect(current()).toBe(GAME_TYPE.DEADLOCK);
    unmount();
    expect(current()).toBeNull();
  });

  it('treats a tournament without a game as Dota 2', () => {
    tournaments.byPk[2] = { pk: 2, name: 'Legacy Cup' };
    renderAt(2);
    expect(current()).toBe(GAME_TYPE.DOTA2);
  });

  it('switches game when navigating to another tournament', () => {
    tournaments.byPk[1] = {
      pk: 1,
      name: 'Deadlock Cup',
      game_type: GAME_TYPE.DEADLOCK,
    };
    tournaments.byPk[2] = {
      pk: 2,
      name: 'Dota Cup',
      game_type: GAME_TYPE.DOTA2,
    };
    renderAt(1);
    expect(current()).toBe(GAME_TYPE.DEADLOCK);
    act(() => {
      void navigate('/tournament/2');
    });
    expect(current()).toBe(GAME_TYPE.DOTA2);
  });
});
