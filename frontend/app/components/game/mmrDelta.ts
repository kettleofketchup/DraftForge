export const LARGE_MMR_CHANGE_THRESHOLD = 0.2;

export interface MmrDelta {
  delta: number;
  pct: number | null;
  isLarge: boolean;
}

export function computeMmrDelta(prior: number, next: number): MmrDelta {
  const delta = next - prior;
  const pct = prior > 0 ? Math.abs(delta) / prior : null;
  return {
    delta,
    pct,
    isLarge: delta !== 0 && pct != null && pct >= LARGE_MMR_CHANGE_THRESHOLD,
  };
}
