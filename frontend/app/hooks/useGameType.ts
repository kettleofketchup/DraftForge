import { useGameTypeStore } from '~/store/gameTypeStore';

/** Read the currently-in-scope game type. Returns null when no game context is set. */
export const useGameType = () => useGameTypeStore((s) => s.currentGameType);
