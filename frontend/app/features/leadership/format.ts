export function formatRating(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

export function placementLabel(placement: number | null): string | null {
  if (placement === null) return null;
  const tens = placement % 100;
  if (tens >= 11 && tens <= 13) return `${placement}th`;
  const suffix =
    { 1: 'st', 2: 'nd', 3: 'rd' }[(placement % 10) as 1 | 2 | 3] ?? 'th';
  return `${placement}${suffix}`;
}
