import type { Forecast } from './schemas';

export function formatForecast(f: Forecast): string {
  return `${f.seat_holders} signed up · expect ~${Math.round(f.expected)} (${f.low}–${f.high})`;
}

export function formatOpenSeats(f: Forecast): string | null {
  if (f.expected_open_seats == null) return null;
  const seats = Math.round(f.expected_open_seats);
  return `~${seats} open ${seats === 1 ? 'seat' : 'seats'}`;
}

export function formatPendingApproval(f: Forecast): string | null {
  if (f.pending_approval === 0) return null;
  return `${f.pending_approval} awaiting approval`;
}
