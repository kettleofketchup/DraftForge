import type { DisplayState } from '~/components/tournament/tournamentBuckets';

/** Card surface shared with the grid skeleton so loading and loaded cards match. */
export const TOURNAMENT_CARD_SURFACE =
  'bg-base-300 w-full max-w-sm h-full flex flex-col card-3d px-4 py-2 rounded-[1.25rem]';

/** Outer cell wrapper shared with the grid skeleton. */
export const TOURNAMENT_CARD_CELL = 'flex items-stretch justify-center p-4 gap-6 w-full h-full';

export type StateTone = 'success' | 'primary' | 'muted';

export const STATE_TILE_CLASSES: Record<StateTone, { media: string; icon: string }> = {
  success: { media: 'bg-success/20 border-success/30', icon: 'text-success' },
  primary: { media: 'bg-primary/20 border-primary/30', icon: 'text-primary' },
  muted: { media: 'bg-muted border-border', icon: 'text-muted-foreground' },
};

export function stateTone(state: DisplayState): StateTone {
  if (state.muted) return 'muted';
  return state.label === 'Past' ? 'success' : 'primary';
}
