import type { Forecast, ScoreStatus } from './schemas';

export function formatShowRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function scoreLabel(row: {
  show_rate: number;
  status: ScoreStatus;
}): string {
  return row.status === 'new' ? 'New' : formatShowRate(row.show_rate);
}

export function formatForecast(f: Forecast): string {
  return `${f.seat_holders} signed up · expect ~${Math.round(f.expected)} (${f.low}–${f.high})`;
}

export function formatOpenSeats(f: Forecast): string | null {
  if (f.expected_open_seats == null) return null;
  const seats = Math.round(f.expected_open_seats);
  return `~${seats} open ${seats === 1 ? 'seat' : 'seats'}`;
}
