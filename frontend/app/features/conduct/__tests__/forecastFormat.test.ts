import { describe, expect, it } from 'vitest';
import {
  formatForecast,
  formatOpenSeats,
  formatPendingApproval,
} from '../forecastFormat';
import { forecast } from './fixtures';

describe('formatForecast', () => {
  it('uses the verbatim summary copy', () => {
    expect(
      formatForecast(
        forecast({ seat_holders: 30, expected: 23.6, low: 21, high: 27 }),
      ),
    ).toBe('30 signed up · expect ~24 (21–27)');
  });
});

describe('formatOpenSeats', () => {
  it('is null without a capacity', () => {
    expect(
      formatOpenSeats(forecast({ capacity: null, expected_open_seats: null })),
    ).toBeNull();
  });

  it('rounds and pluralises', () => {
    expect(formatOpenSeats(forecast({ expected_open_seats: 0.6 }))).toBe(
      '~1 open seat',
    );
    expect(formatOpenSeats(forecast({ expected_open_seats: 3.2 }))).toBe(
      '~3 open seats',
    );
  });
});

describe('formatPendingApproval', () => {
  it('is null when nobody is pending', () => {
    expect(formatPendingApproval(forecast({ pending_approval: 0 }))).toBeNull();
  });

  it('counts pending signups', () => {
    expect(formatPendingApproval(forecast({ pending_approval: 2 }))).toBe(
      '2 awaiting approval',
    );
  });
});
