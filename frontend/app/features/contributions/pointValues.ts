import type { PointValueRow } from './schemas';

export interface PointValueDescription {
  label: 'Default' | 'Changed';
  canReset: boolean;
}

export function describePointValue(row: PointValueRow): PointValueDescription {
  return row.is_default
    ? { label: 'Default', canReset: false }
    : { label: 'Changed', canReset: true };
}
