import type { GameTypeValue } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';

/** Put a page's game in scope, as the tournament/event/league pages do. */
export function withGameType(gameType: GameTypeValue | null): void {
  useGameTypeStore.setState({ currentGameType: gameType });
}

export function resetGameType(): void {
  useGameTypeStore.setState({ currentGameType: null });
}
