import { create } from 'zustand';

import type { GameTypeValue } from '~/components/game/constants';

interface GameTypeState {
  /** Game type currently in scope (e.g. set on event page mount). null when out of any game context. */
  currentGameType: GameTypeValue | null;
  setCurrentGameType: (gt: GameTypeValue | null) => void;
}

export const useGameTypeStore = create<GameTypeState>((set) => ({
  currentGameType: null,
  setCurrentGameType: (gt) => set({ currentGameType: gt }),
}));
