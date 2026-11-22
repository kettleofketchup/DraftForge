import { format } from 'date-fns';

export function formatMmrDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : format(date, 'd MMM yyyy');
}
