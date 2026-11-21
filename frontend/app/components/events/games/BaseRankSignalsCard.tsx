import type { ReactNode } from 'react';

import type { EventSignupType } from '~/components/events/schemas';
import { GAME_LABEL, type GameTypeValue } from '~/components/game/constants';

interface BaseRankSignalsCardProps {
  signup: EventSignupType;
  /** Game whose org MMR `signup.org_user_mmr` holds; labels the prior row. */
  gameType: GameTypeValue;
  /** Game-specific rows rendered after the universal prior org MMR row. */
  children?: ReactNode;
  /** Optional warning banner rendered after children — for game-specific signal mismatches. */
  warning?: ReactNode;
}

/**
 * Universal "Rank Signals" card shown for every game. Always renders the prior
 * org MMR row (`signup.org_user_mmr`, resolved server-side for the event's
 * game). Game-specific cards compose this base and add rows via `children`.
 */
export function BaseRankSignalsCard({
  signup,
  gameType,
  children,
  warning,
}: BaseRankSignalsCardProps) {
  const priorMmr = signup.org_user_mmr;

  return (
    <div
      data-testid="rank-signals"
      className="bg-base-300 border border-border rounded-lg p-4 space-y-2 text-sm"
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        Rank Signals
      </div>

      <div
        className="flex justify-between items-center"
        data-testid="rank-signals-prior-mmr"
      >
        <span className="text-muted-foreground">
          Prior {GAME_LABEL[gameType]} org MMR
        </span>
        <span
          className={priorMmr != null ? 'font-mono' : 'text-muted-foreground'}
        >
          {priorMmr != null ? priorMmr.toLocaleString() : '—'}
        </span>
      </div>

      {children}

      {warning}
    </div>
  );
}
