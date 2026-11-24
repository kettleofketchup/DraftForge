import { DEFAULT_MMR_BOUNDS } from '~/components/game/constants';

export interface MmrBound {
  value: number | null;
  error: string | null;
}

const [MIN_MMR, MAX_MMR] = DEFAULT_MMR_BOUNDS;

/** Parses an MMR filter input; blank means no bound. */
export function parseMmrBound(text: string): MmrBound {
  const trimmed = text.trim();
  if (trimmed === '') return { value: null, error: null };
  if (!/^\d+$/.test(trimmed))
    return { value: null, error: 'MMR must be a whole number' };
  const value = Number(trimmed);
  if (value < MIN_MMR || value > MAX_MMR)
    return { value: null, error: `MMR must be ${MIN_MMR}–${MAX_MMR}` };
  return { value, error: null };
}

/** First problem with a min/max pair, or null when it can be applied. */
export function validateMmrRange(min: MmrBound, max: MmrBound): string | null {
  if (min.error) return `Min: ${min.error}`;
  if (max.error) return `Max: ${max.error}`;
  if (min.value != null && max.value != null && min.value > max.value)
    return 'Max MMR must be at least the min MMR';
  return null;
}
