import { QueryClient, type QueryKey } from '@tanstack/react-query';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  conductKeys,
  invalidateConductQueries,
  removeFeatureQueries,
  standingKeys,
} from '../queryKeys';

const attendance3 = conductKeys.attendance(3, 9, 5);
const forecast3 = conductKeys.forecast(3, 9, 5);
const member3 = conductKeys.member(3, 9, 7, { limit: 50, offset: 0 });
const conductBoard3 = standingKeys.leaderboard(
  3,
  9,
  'conduct',
  'show_rate',
  'current',
);
const contribBoard3 = standingKeys.leaderboard(
  3,
  9,
  'contribution',
  'points',
  'all',
);
const forecast4 = conductKeys.forecast(4, 9, 6);
const conductBoard4 = standingKeys.leaderboard(
  4,
  9,
  'conduct',
  'show_rate',
  'current',
);

const seeded: QueryKey[] = [
  attendance3,
  forecast3,
  member3,
  conductBoard3,
  contribBoard3,
  forecast4,
  conductBoard4,
];

describe('conduct event query keys', () => {
  let client: QueryClient;

  const invalid = (key: QueryKey): boolean =>
    client.getQueryState(key)?.isInvalidated ?? false;

  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    for (const key of seeded) client.setQueryData(key, { seeded: true });
  });

  it('builds attendance and forecast keys under the event key', () => {
    expect(conductKeys.event(3, 9, 5)).toEqual([
      'org-conduct',
      3,
      9,
      'event',
      5,
    ]);
    expect(attendance3).toEqual([
      'org-conduct',
      3,
      9,
      'event',
      5,
      'attendance',
    ]);
    expect(forecast3).toEqual(['org-conduct', 3, 9, 'event', 5, 'forecast']);
  });

  it('refreshes one org’s conduct and conduct standing queries', async () => {
    await invalidateConductQueries(client, 3);
    expect(invalid(attendance3)).toBe(true);
    expect(invalid(forecast3)).toBe(true);
    expect(invalid(member3)).toBe(true);
    expect(invalid(conductBoard3)).toBe(true);
    expect(invalid(contribBoard3)).toBe(false);
    expect(invalid(forecast4)).toBe(false);
    expect(invalid(conductBoard4)).toBe(false);
  });

  it('except keeps the given key and everything under it', async () => {
    await invalidateConductQueries(client, 3, { except: attendance3 });
    expect(invalid(attendance3)).toBe(false);
    expect(invalid(forecast3)).toBe(true);
    expect(invalid(member3)).toBe(true);
    expect(invalid(conductBoard3)).toBe(true);
    expect(invalid(contribBoard3)).toBe(false);
  });

  it('except with an event prefix keeps both event queries', async () => {
    await invalidateConductQueries(client, 3, {
      except: conductKeys.event(3, 9, 5),
    });
    expect(invalid(attendance3)).toBe(false);
    expect(invalid(forecast3)).toBe(false);
    expect(invalid(member3)).toBe(true);
  });

  it('without an org refreshes conduct queries of every org but no contribution board', async () => {
    await invalidateConductQueries(client, null);
    expect(invalid(attendance3)).toBe(true);
    expect(invalid(forecast4)).toBe(true);
    expect(invalid(conductBoard3)).toBe(true);
    expect(invalid(conductBoard4)).toBe(true);
    expect(invalid(contribBoard3)).toBe(false);
  });

  it('event keys nest under conductKeys.all so removeFeatureQueries drops them', () => {
    expect(attendance3.slice(0, 3)).toEqual(conductKeys.all(3, 9));
    removeFeatureQueries(client, 3);
    expect(client.getQueryState(attendance3)).toBeUndefined();
    expect(client.getQueryState(forecast3)).toBeUndefined();
    expect(client.getQueryState(forecast4)).toBeDefined();
  });
});
