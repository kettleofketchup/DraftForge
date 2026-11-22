import { formatMetricValue } from '~/features/standing/format';
import type { ScoreStatus } from './schemas';

export function formatShowRate(row: {
  show_rate: number;
  status: ScoreStatus;
}): string {
  return formatMetricValue(
    { value: row.show_rate, status: row.status === 'new' ? 'new' : 'ranked' },
    'percent',
  );
}
