import { Badge } from '~/components/ui/badge';
import { RolePositions } from '~/components/user/positions';
import { dotaProfileToPositions } from '~/components/user/UserEventStrip';
import type { UserType } from '~/components/user/types';
import type { EventSignupType } from '~/components/events/schemas';

import { BaseRankSignalsCard } from '../BaseRankSignalsCard';

interface Dota2RankSignalsCardProps {
  signup: EventSignupType;
}

/**
 * Dota 2-specific rank signals — composes the universal `BaseRankSignalsCard`
 * (which renders the prior approved MMR row) and adds Dota-specific rows on
 * top: self-reported MMR, medal + suggested range, battle-cup tier, and
 * positions.
 */
export function Dota2RankSignalsCard({ signup }: Dota2RankSignalsCardProps) {
  const profile = signup.dota_profile;
  const [rangeLow, rangeHigh] = signup.suggested_mmr_range;

  const positionsUser = profile?.positions
    ? ({ ...({} as UserType), positions: dotaProfileToPositions(profile.positions) } as UserType)
    : null;

  const isPrevious = profile?.rank_status === 'previous';

  return (
    <BaseRankSignalsCard signup={signup}>
      {/* Self-Reported MMR (Dota — pulled from PlayerDotaProfile.mmr) */}
      <div className="flex justify-between items-center" data-testid="rank-signals-self-report">
        <span className="text-muted-foreground">Self-Reported MMR</span>
        <span className={profile?.mmr != null ? 'font-mono' : 'text-muted-foreground'}>
          {profile?.mmr != null ? profile.mmr.toLocaleString() : '—'}
        </span>
      </div>

      {/* Rank (medal) */}
      <div className="flex justify-between items-center" data-testid="rank-signals-medal">
        <span className="text-muted-foreground">Rank</span>
        {profile?.rank_medal ? (
          <span className="flex items-center">
            <Badge
              variant="outline"
              className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30"
            >
              {profile.rank_medal}
            </Badge>
            <span className="text-xs text-muted-foreground font-mono ml-2">
              {rangeLow.toLocaleString()}&ndash;{rangeHigh.toLocaleString()}
              {isPrevious ? ' (previous)' : ''}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground">&mdash;</span>
        )}
      </div>

      {/* Battle Cup Tier */}
      <div className="flex justify-between items-center" data-testid="rank-signals-battle-cup">
        <span className="text-muted-foreground">Battle Cup Tier</span>
        {profile?.rank_status === 'never' && profile?.battle_cup_tier != null ? (
          <Badge
            variant="outline"
            className="px-1.5 py-0 text-xs font-medium text-blue-300 border-blue-500/30"
          >
            Tier {profile.battle_cup_tier}
          </Badge>
        ) : (
          <span className="text-muted-foreground">&mdash;</span>
        )}
      </div>

      {/* Positions (only when set) */}
      {positionsUser?.positions && (
        <div
          className="flex justify-between items-center"
          data-testid="rank-signals-positions"
        >
          <span className="text-muted-foreground">Positions</span>
          <RolePositions user={positionsUser} compact disableTooltips unranked />
        </div>
      )}
    </BaseRankSignalsCard>
  );
}
