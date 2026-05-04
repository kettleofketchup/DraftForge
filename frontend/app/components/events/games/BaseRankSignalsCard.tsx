import type { ReactNode } from 'react';

import type { EventSignupType } from '~/components/events/schemas';

interface BaseRankSignalsCardProps {
  signup: EventSignupType;
  /** Game-specific rows rendered after the universal Previously Approved MMR row. */
  children?: ReactNode;
}

/**
 * Universal "Rank Signals" card shown for every game. Always renders the prior
 * approved MMR row (driven by `signup.org_user_mmr`, which exists on every
 * OrgUser regardless of game). Game-specific cards (e.g. `Dota2RankSignalsCard`)
 * compose this base and inject their own rows via `children`.
 *
 * The dispatcher (`./RankSignalsCard`) returns this directly for non-Dota games.
 */
export function BaseRankSignalsCard({ signup, children }: BaseRankSignalsCardProps) {
  const priorMmr = signup.org_user_mmr;

  return (
    <div
      data-testid="rank-signals"
      className="bg-base-300 border border-border rounded-lg p-4 space-y-2 text-sm"
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        Rank Signals
      </div>

      {/* Previously Approved MMR — universal across games */}
      <div className="flex justify-between items-center" data-testid="rank-signals-prior-mmr">
        <span className="text-muted-foreground">Previously Approved MMR</span>
        <span className={priorMmr != null ? 'font-mono' : 'text-muted-foreground'}>
          {priorMmr != null ? priorMmr.toLocaleString() : '—'}
        </span>
      </div>

      {children}
    </div>
  );
}
