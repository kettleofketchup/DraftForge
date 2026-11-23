import { QueryClient, type QueryKey } from '@tanstack/react-query';
import { beforeEach, describe, expect, it } from 'vitest';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import {
  invalidateLeadershipQueries,
  leadershipKeys,
  removeFeatureQueries,
  standingKeys,
} from '../queryKeys';

const member = leadershipKeys.member(4, 9, 7);
const pending = leadershipKeys.pending(4, 9, null);
const pendingEvent = leadershipKeys.pending(4, 9, 5);
const settings = leadershipKeys.settings(4, 9);
const traits = leadershipKeys.traits(4, 9);
const eventReviews = leadershipKeys.eventReviews(4, 9, 5);
const leadershipBoard = standingKeys.leaderboard(
  4,
  9,
  'leadership',
  'rating',
  'current',
);
const conductBoard = standingKeys.leaderboard(
  4,
  9,
  'conduct',
  'show_rate',
  'current',
);
const otherOrgMine = leadershipKeys.mine(8, 9);
const event5 = ['event', 5] as const;
const event6 = ['event', 6] as const;
const org4 = organizationQueryKey(4);
const org8 = organizationQueryKey(8);

const seeded: QueryKey[] = [
  member,
  pending,
  pendingEvent,
  settings,
  traits,
  eventReviews,
  leadershipBoard,
  conductBoard,
  otherOrgMine,
  event5,
  event6,
  org4,
  org8,
];

describe('leadership query keys', () => {
  let client: QueryClient;

  const invalid = (key: QueryKey): boolean =>
    client.getQueryState(key)?.isInvalidated ?? false;

  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    for (const key of seeded) client.setQueryData(key, { seeded: true });
  });

  it('nests every key under all()', () => {
    const all = leadershipKeys.all(4, 9);
    expect(all).toEqual(['org-leadership', 4, 9]);
    expect(member).toEqual(['org-leadership', 4, 9, 'member', 7]);
    expect(pending).toEqual(['org-leadership', 4, 9, 'pending', null]);
    expect(pendingEvent).toEqual(['org-leadership', 4, 9, 'pending', 5]);
    expect(leadershipKeys.mine(4, 9)).toEqual(['org-leadership', 4, 9, 'mine']);
    expect(eventReviews).toEqual(['org-leadership', 4, 9, 'event-reviews', 5]);
    expect(settings).toEqual(['org-leadership', 4, 9, 'settings']);
    expect(traits).toEqual(['org-leadership', 4, 9, 'traits']);
  });

  it('refreshes one org’s leadership queries, leadership boards and the event', async () => {
    await invalidateLeadershipQueries(client, 4, {
      eventId: 5,
      except: settings,
    });
    expect(invalid(member)).toBe(true);
    expect(invalid(pending)).toBe(true);
    expect(invalid(pendingEvent)).toBe(true);
    expect(invalid(traits)).toBe(true);
    expect(invalid(eventReviews)).toBe(true);
    expect(invalid(leadershipBoard)).toBe(true);
    expect(invalid(event5)).toBe(true);
    expect(invalid(settings)).toBe(false);
    expect(invalid(conductBoard)).toBe(false);
    expect(invalid(otherOrgMine)).toBe(false);
    expect(invalid(event6)).toBe(false);
    expect(invalid(org4)).toBe(false);
    expect(invalid(org8)).toBe(false);
  });

  it('leaves events alone without an event id', async () => {
    await invalidateLeadershipQueries(client, 4);
    expect(invalid(settings)).toBe(true);
    expect(invalid(event5)).toBe(false);
    expect(invalid(event6)).toBe(false);
  });

  it('refreshes the org payload when asked', async () => {
    await invalidateLeadershipQueries(client, 4, { org: true });
    expect(invalid(org4)).toBe(true);
    expect(invalid(org8)).toBe(false);
    expect(invalid(member)).toBe(true);
  });

  it('removeFeatureQueries drops the org’s leadership queries', () => {
    removeFeatureQueries(client, 4);
    expect(client.getQueryState(member)).toBeUndefined();
    expect(client.getQueryState(settings)).toBeUndefined();
    expect(client.getQueryState(otherOrgMine)).toBeDefined();
  });
});
