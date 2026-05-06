import { GAME_TYPE } from '~/components/game/constants';
import type { EventSignupType } from '~/components/events/schemas';
import { useGameType } from '~/hooks/useGameType';

import { BaseRankSignalsCard } from './BaseRankSignalsCard';
import { Dota2RankSignalsCard } from './dota2/Dota2RankSignalsCard';

interface RankSignalsCardProps {
  signup: EventSignupType;
}

/**
 * Game-type-aware dispatcher. Returns the universal `BaseRankSignalsCard`
 * (prior approved MMR row only) by default, and swaps in a game-specific card
 * with extra rows when the in-scope game has one. The in-scope game type is
 * set via `setCurrentGameType` on the event page.
 */
export function RankSignalsCard({ signup }: RankSignalsCardProps) {
  const gameType = useGameType();

  if (gameType === GAME_TYPE.DOTA2) {
    return <Dota2RankSignalsCard signup={signup} />;
  }

  return <BaseRankSignalsCard signup={signup} />;
}
