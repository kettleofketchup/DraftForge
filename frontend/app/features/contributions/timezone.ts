import { ALL_TIME } from './schemas';

export function safeTimeZone(tz: string | undefined): string {
  if (!tz) return 'UTC';
  try {
    new Intl.DateTimeFormat('en', { timeZone: tz });
    return tz;
  } catch {
    return 'UTC';
  }
}

export interface PeriodOption {
  value: string;
  label: string;
}

const monthLabelFormat = new Intl.DateTimeFormat('en-US', {
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

const shortMonthFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  timeZone: 'UTC',
});

function monthDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 15));
}

/** "2026-10" -> "October 2026"; the month itself is already org-local. */
export function monthLabel(value: string): string {
  const date = monthDate(value);
  return date ? monthLabelFormat.format(date) : value;
}

export function shortMonthLabel(value: string): string {
  const date = monthDate(value);
  return date ? shortMonthFormat.format(date) : value;
}

function currentMonth(tz: string, now: Date): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: safeTimeZone(tz),
    year: 'numeric',
    month: 'numeric',
  }).formatToParts(now);
  const get = (type: string): number =>
    Number(parts.find((p) => p.type === type)?.value);
  return { year: get('year'), month: get('month') };
}

export function periodOptions(
  tz: string | undefined,
  now: Date = new Date(),
): PeriodOption[] {
  const { year, month } = currentMonth(safeTimeZone(tz), now);
  const options: PeriodOption[] = [{ value: ALL_TIME, label: 'All time' }];
  for (let i = 0; i < 12; i++) {
    const index = year * 12 + (month - 1) - i;
    const value = `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
    options.push({ value, label: monthLabel(value) });
  }
  return options;
}

export function formatOrgDate(iso: string, tz: string | undefined): string {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeZone: safeTimeZone(tz),
  }).format(new Date(iso));
}

/** The org-local calendar date (YYYY-MM-DD) of `now`. */
export function todayInZone(
  tz: string | undefined,
  now: Date = new Date(),
): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: safeTimeZone(tz),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: string): string =>
    parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function dateInZone(iso: string, tz: string | undefined): string {
  return todayInZone(tz, new Date(iso));
}
