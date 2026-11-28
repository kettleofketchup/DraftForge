import { z } from 'zod';

const DEFAULT_RANGE_DAYS = 90;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseCalendarDate(value: string): Date | null {
  const match = DATE_RE.exec(value);
  if (!match) return null;
  const [, y, m, d] = match.map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (
    date.getUTCFullYear() !== y ||
    date.getUTCMonth() !== m - 1 ||
    date.getUTCDate() !== d
  ) {
    return null;
  }
  return date;
}

function formatUtcDate(date: Date): string {
  const y = String(date.getUTCFullYear()).padStart(4, '0');
  const m = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d = String(date.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(value: string, days: number): string {
  const date = parseCalendarDate(value);
  if (!date) throw new Error(`Invalid calendar date: ${value}`);
  date.setUTCDate(date.getUTCDate() + days);
  return formatUtcDate(date);
}

const exportDateSchema = z
  .string()
  .min(1, { message: 'Pick a date.' })
  .refine((v) => parseCalendarDate(v) !== null, {
    message: 'Pick a valid date.',
  });

export const exportRangeSchema = z
  .object({ from: exportDateSchema, to: exportDateSchema })
  .refine(({ from, to }) => to >= from, {
    message: 'To must be on or after From.',
    path: ['to'],
  });

export type ExportRange = z.infer<typeof exportRangeSchema>;

export interface ExportParams {
  since: string;
  until: string;
}

export function toExportParams({ from, to }: ExportRange): ExportParams {
  return { since: from, until: addDays(to, 1) };
}

export function defaultExportRange(today: Date): ExportRange {
  const to = formatUtcDate(
    new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())),
  );
  return { from: addDays(to, -DEFAULT_RANGE_DAYS), to };
}
