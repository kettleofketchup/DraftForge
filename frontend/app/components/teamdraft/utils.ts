import type { ActiveDraftType } from '~/components/user';
import type { UserType } from '~/index';
import type { DraftRoundType } from './types';

/**
 * Build the URL for navigating to an active draft.
 */
export function getDraftUrl(draft: ActiveDraftType): string {
  if (draft.type === 'team_draft') {
    return `/tournament/${draft.tournament_pk}/teams/draft`;
  }
  return `/herodraft/${draft.herodraft_pk}`;
}

/**
 * Get a display label for the draft type.
 */
export function getDraftLabel(draft: ActiveDraftType): string {
  if (draft.type === 'team_draft') {
    return `Team Draft (Tournament ${draft.tournament_pk})`;
  }
  return `Hero Draft (Game ${draft.game_pk})`;
}

export function deriveDraftIndex(
  rounds: ReadonlyArray<{ pk: number | null }> | null | undefined,
  curRoundPk: number | null | undefined,
): number {
  if (!rounds || curRoundPk == null) return -1;
  return rounds.findIndex((r) => r.pk === curRoundPk);
}

export interface ViewedRoundResult {
  round: DraftRoundType | null;
  moved: { captain: UserType | null; pickNumber: number } | null;
}

export function resolveViewedRound(
  rounds: ReadonlyArray<DraftRoundType>,
  viewed: DraftRoundType | null | undefined,
  opts: { autoAdvance: boolean; latestRoundPk: number | null | undefined; forceJumpToRoundPk: number | null },
): ViewedRoundResult {
  const refreshed = rounds.find((r) => r.pk === viewed?.pk) ?? null;
  if (opts.forceJumpToRoundPk != null) {
    const target = rounds.find((r) => r.pk === opts.forceJumpToRoundPk);
    if (target) {
      const moved =
        refreshed && viewed && refreshed.pick_number != null && refreshed.pick_number !== viewed.pick_number
          ? { captain: (refreshed.captain ?? null) as UserType | null, pickNumber: refreshed.pick_number }
          : null;
      return { round: target, moved };
    }
  }
  if (opts.autoAdvance && opts.latestRoundPk != null) {
    const latest = rounds.find((r) => r.pk === opts.latestRoundPk);
    if (latest) return { round: latest, moved: null };
  }
  return { round: refreshed, moved: null };
}
