import { GAME_TYPE } from '~/components/game/constants';
import type { EventSignupType } from '~/components/events/schemas';
import { useGameType } from '~/hooks/useGameType';

import { Dota2RankSignalsCard } from './dota2/Dota2RankSignalsCard';

interface RankSignalsCardProps {
  signup: EventSignupType;
}

/**
 * Game-type-aware dispatcher. Renders the rank-signals card matching whatever
 * game is currently in scope (set via `setCurrentGameType` on the event page).
 * Returns null when the in-scope game has no specialized card yet (e.g. Deadlock).
 */
export function RankSignalsCard({ signup }: RankSignalsCardProps) {
  const gameType = useGameType();

  if (gameType === GAME_TYPE.DOTA2) {
    return <Dota2RankSignalsCard signup={signup} />;
  }

  return null;
}
