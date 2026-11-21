import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import { ALL_TIME } from '~/features/contributions/schemas';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getStandingLeaderboard } from '../api';
import type { Metric } from '../schemas';

const points: Metric = {
  key: 'points',
  label: 'Points',
  format: 'int',
  periodic: true,
  default: true,
};
const showRate: Metric = {
  key: 'show_rate',
  label: 'Show rate',
  format: 'percent',
  periodic: false,
  default: true,
};

const board = {
  track: 'contribution',
  metric: points,
  period: '2026-10',
  total: 20,
  rows: [],
  rows_visible: true,
  own_row: null,
};

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ data: board });
});

describe('getStandingLeaderboard', () => {
  it('sends the period for a periodic metric', async () => {
    const result = await getStandingLeaderboard(
      1,
      'contribution',
      points,
      '2026-10',
    );
    expect(get).toHaveBeenCalledWith(
      '/organizations/1/standing/contribution/leaderboard/',
      { params: { metric: 'points', period: '2026-10' } },
    );
    expect(result.total).toBe(20);
  });

  it('omits the period for all time', async () => {
    await getStandingLeaderboard(1, 'contribution', points, ALL_TIME);
    expect(get).toHaveBeenCalledWith(
      '/organizations/1/standing/contribution/leaderboard/',
      { params: { metric: 'points' } },
    );
  });

  it('omits the period for a non-periodic metric', async () => {
    get.mockResolvedValue({
      data: { ...board, track: 'conduct', metric: showRate, total: null },
    });
    await getStandingLeaderboard(2, 'conduct', showRate, '2026-10');
    expect(get).toHaveBeenCalledWith(
      '/organizations/2/standing/conduct/leaderboard/',
      { params: { metric: 'show_rate' } },
    );
  });

  it('rejects a malformed payload', async () => {
    get.mockResolvedValue({ data: { ...board, rows: 'nope' } });
    await expect(
      getStandingLeaderboard(1, 'contribution', points, '2026-10'),
    ).rejects.toBeInstanceOf(ZodError);
  });
});
