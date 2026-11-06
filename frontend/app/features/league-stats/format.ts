export type WinRateTone = 'good' | 'bad' | 'neutral';

export function winRatePercent(winRate: number): number {
  return Math.round(winRate * 100);
}

export function winRateTone(winRate: number): WinRateTone {
  const pct = winRatePercent(winRate);
  if (pct >= 55) return 'good';
  if (pct <= 45) return 'bad';
  return 'neutral';
}

export function formatWinRate(winRate: number): string {
  return `${winRatePercent(winRate)}%`;
}

export const toneClass: Record<WinRateTone, string> = {
  good: 'text-success',
  bad: 'text-destructive',
  neutral: '',
};
