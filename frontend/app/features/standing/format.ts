import type { MetricFormat, StandingRow } from './schemas';

function formatNumber(value: number, format: MetricFormat): string {
  switch (format) {
    case 'percent':
      return `${Math.round(value * 100)}%`;
    case 'score5':
      return value.toFixed(1);
    case 'int':
      return value.toLocaleString('en-US');
  }
}

export function formatMetricValue(
  row: Pick<StandingRow, 'value' | 'status'>,
  format: MetricFormat,
): string {
  if (row.status === 'new' || row.value === null) return 'New';
  return formatNumber(row.value, format);
}

export function formatTotal(total: number, format: MetricFormat): string {
  return formatNumber(total, format);
}

export const FEEDBACK_PRIVATE_NOTE = 'Your org keeps captain feedback private.';
