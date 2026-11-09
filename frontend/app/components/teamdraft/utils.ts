import type { ActiveDraftType } from '~/components/user';

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
