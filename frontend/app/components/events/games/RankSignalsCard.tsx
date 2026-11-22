import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { useContextGameType } from '~/hooks/useGameType';

import { BaseRankSignalsCard } from './BaseRankSignalsCard';
import { DeadlockRankSignalsCard } from './DeadlockRankSignalsCard';
import { Dota2RankSignalsCard } from './dota2/Dota2RankSignalsCard';

interface RankSignalsCardProps {
  signup: EventSignupType;
}

/** The page's game-specific card, else the universal `BaseRankSignalsCard`. */
export function RankSignalsCard({ signup }: RankSignalsCardProps) {
  const gameType = useContextGameType();
  if (gameType === GAME_TYPE.DOTA2) {
    return <Dota2RankSignalsCard signup={signup} />;
  }
  if (gameType === GAME_TYPE.DEADLOCK) {
    return <DeadlockRankSignalsCard signup={signup} />;
  }
  return <BaseRankSignalsCard signup={signup} gameType={gameType} />;
}
