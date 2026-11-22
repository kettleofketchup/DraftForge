import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { Badge } from '~/components/ui/badge';

import { BaseRankSignalsCard } from './BaseRankSignalsCard';

interface DeadlockRankSignalsCardProps {
  signup: EventSignupType;
}

/** Deadlock rank signals: the player's self-reported rank and when it was set. */
export function DeadlockRankSignalsCard({
  signup,
}: DeadlockRankSignalsCardProps) {
  const rank = signup.self_reported_rank ?? null;
  const rankDate = signup.self_reported_rank_date ?? null;

  return (
    <BaseRankSignalsCard signup={signup} gameType={GAME_TYPE.DEADLOCK}>
      <div
        className="flex justify-between items-center"
        data-testid="rank-signals-deadlock-rank"
      >
        <span className="text-muted-foreground">Self-Reported Rank</span>
        {rank ? (
          <span className="flex items-center">
            <Badge
              data-testid="rank-signals-deadlock-rank-value"
              variant="outline"
              className="px-1.5 py-0 text-xs font-medium text-rank-ranked border-rank-ranked/30"
            >
              {rank}
            </Badge>
            {rankDate && (
              <span className="text-xs text-muted-foreground font-mono ml-2">
                {rankDate}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">&mdash;</span>
        )}
      </div>
    </BaseRankSignalsCard>
  );
}
