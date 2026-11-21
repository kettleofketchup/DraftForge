import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';

import { BaseRankSignalsCard } from './BaseRankSignalsCard';
import { DeadlockRankSignalsCard } from './DeadlockRankSignalsCard';
import { Dota2RankSignalsCard } from './dota2/Dota2RankSignalsCard';

interface RankSignalsCardProps {
  signup: EventSignupType;
  gameType: GameTypeValue;
}

/**
 * Game-aware dispatcher: a game-specific card when the event's game has one,
 * otherwise the universal `BaseRankSignalsCard`.
 */
export function RankSignalsCard({ signup, gameType }: RankSignalsCardProps) {
  if (gameType === GAME_TYPE.DOTA2) {
    return <Dota2RankSignalsCard signup={signup} />;
  }
  if (gameType === GAME_TYPE.DEADLOCK) {
    return <DeadlockRankSignalsCard signup={signup} />;
  }
  return <BaseRankSignalsCard signup={signup} gameType={gameType} />;
}
