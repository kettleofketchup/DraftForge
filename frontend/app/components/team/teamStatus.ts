export type TeamStatus = 'live' | 'winner' | 'eliminated';

export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

export function teamStatus(placement: number | null | undefined): TeamStatus {
  if (placement == null) return 'live';
  return placement === 1 ? 'winner' : 'eliminated';
}

export function teamStatusLabel(placement: number | null | undefined): string {
  if (placement == null) return 'In tournament';
  if (placement === 1) return 'Winner';
  return `Eliminated · ${ordinal(placement)}`;
}
