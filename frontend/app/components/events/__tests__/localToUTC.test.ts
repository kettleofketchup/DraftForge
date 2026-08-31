import { describe, expect, it } from 'vitest';
import { localToUTC } from '../schemas';

describe('localToUTC', () => {
  it.each([
    ['2026-09-01T02:00', 'America/New_York', '2026-09-01T06:00:00.000Z'],
    ['2026-08-31T23:00', 'Europe/Berlin', '2026-08-31T21:00:00.000Z'],
    ['2026-09-30T20:00', 'Asia/Tokyo', '2026-09-30T11:00:00.000Z'],
    ['2026-09-30T20:00', 'Pacific/Auckland', '2026-09-30T07:00:00.000Z'],
    ['2026-12-31T23:00', 'Europe/Berlin', '2026-12-31T22:00:00.000Z'],
    ['2026-09-15T02:00', 'America/New_York', '2026-09-15T06:00:00.000Z'],
    ['2026-03-29T19:00', 'Europe/Berlin', '2026-03-29T17:00:00.000Z'],
  ])('converts %s in %s', (local, tz, expected) => {
    expect(localToUTC(local, tz)).toBe(expected);
  });
});
