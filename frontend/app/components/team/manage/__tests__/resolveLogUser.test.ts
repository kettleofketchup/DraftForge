import { describe, expect, it } from 'vitest';
import type { UserEntry } from '~/store/userCacheTypes';
import { isUnresolvedLogUser, resolveLogUser } from '../resolveLogUser';
import { managedTeam, people, UNRESOLVABLE_PK } from './fixtures';

const cacheEntry: UserEntry = {
  pk: 42,
  username: 'cached_user',
  orgData: {},
  leagueData: {},
  _fetchedAt: 0,
} as UserEntry;
const cache = {
  getById: (pk: number): UserEntry | undefined =>
    pk === cacheEntry.pk ? cacheEntry : undefined,
};

describe('resolveLogUser', () => {
  it.each([
    ['member', people.member],
    ['stand-in', people.standin],
    ['dropout', people.dropout],
  ])('finds a %s on the team roster', (_label, user) => {
    expect(resolveLogUser(user.pk, { team: managedTeam })).toBe(user);
  });

  it('finds a captain or deputy who is not on the member lists', () => {
    const team = {
      ...managedTeam,
      members: [],
      captain: people.outsider,
    };
    expect(resolveLogUser(people.outsider.pk, { team })).toBe(people.outsider);
  });

  it('prefers the roster over tournament users', () => {
    const other = { ...people.member, username: 'other_name' };
    expect(
      resolveLogUser(people.member.pk, {
        team: managedTeam,
        tournamentUsers: [other],
      }),
    ).toBe(people.member);
  });

  it('uses tournament users when the roster misses', () => {
    const user = { pk: 42, username: 'tournament_user' };
    expect(
      resolveLogUser(42, { team: managedTeam, tournamentUsers: [user], cache }),
    ).toBe(user);
  });

  it('treats a {pk} stub as unresolved and falls through', () => {
    expect(resolveLogUser(42, { tournamentUsers: [{ pk: 42 }], cache })).toBe(
      cacheEntry,
    );
  });

  it('skips a roster stub too', () => {
    const team = { ...managedTeam, members: [{ pk: 42, username: null }] };
    expect(resolveLogUser(42, { team, cache })).toBe(cacheEntry);
  });

  it('uses the cache last', () => {
    expect(resolveLogUser(42, { team: managedTeam, cache })).toBe(cacheEntry);
  });

  it('falls back to a Player #pk label', () => {
    const result = resolveLogUser(UNRESOLVABLE_PK, {
      team: managedTeam,
      tournamentUsers: [{ pk: UNRESOLVABLE_PK }],
      cache,
    });
    expect(result).toEqual({
      pk: UNRESOLVABLE_PK,
      fallbackLabel: 'Player #99',
    });
    expect(isUnresolvedLogUser(result)).toBe(true);
    expect(isUnresolvedLogUser(people.member)).toBe(false);
  });
});
