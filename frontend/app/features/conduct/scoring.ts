import type { ScoreStatus } from './schemas';

export function formatShowRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function scoreLabel(row: {
  show_rate: number;
  status: ScoreStatus;
}): string {
  return row.status === 'new' ? 'New' : formatShowRate(row.show_rate);
}
