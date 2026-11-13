import { describe, expect, it } from 'vitest';
import type { TournamentType } from '~/components/tournament/types';
import {
  defaultOrgScope,
  groupOrganizations,
  isDefaultOrgScope,
  isExplicitOrgScope,
  orgScopeParam,
  orgScopeRequest,
  orgScopeValue,
  parseOrgScope,
  showsSignupsOpenBadge,
} from '../orgScope';

function tournament(orgId: number | null, signupsOpen: boolean): TournamentType {
  return {
    pk: 1,
    name: 'Cup',
    date_played: '2099-01-01T00:00:00Z',
    state: 'future',
    signups_open: signupsOpen,
    league: {
      pk: 1,
      name: 'League',
      organization_name: 'Org',
      organization_id: orgId,
      organization_logo: null,
    },
  } as TournamentType;
}

describe('parseOrgScope', () => {
  it('defaults to mine when logged in and all when logged out', () => {
    expect(parseOrgScope(null, true)).toEqual({ kind: 'mine' });
    expect(parseOrgScope(null, false)).toEqual({ kind: 'all' });
  });

  it('reads mine, all and organization ids', () => {
    expect(parseOrgScope('mine', true)).toEqual({ kind: 'mine' });
    expect(parseOrgScope('all', true)).toEqual({ kind: 'all' });
    expect(parseOrgScope('30', true)).toEqual({ kind: 'org', id: 30 });
    expect(parseOrgScope('30', false)).toEqual({ kind: 'org', id: 30 });
  });

  it('treats mine as all when logged out', () => {
    expect(parseOrgScope('mine', false)).toEqual({ kind: 'all' });
  });

  it('falls back to the default for invalid values', () => {
    for (const raw of ['abc', '0', '-1', '', '1.5']) {
      expect(parseOrgScope(raw, true)).toEqual({ kind: 'mine' });
      expect(parseOrgScope(raw, false)).toEqual({ kind: 'all' });
    }
  });
});

describe('isExplicitOrgScope', () => {
  it('is true only for values that do not depend on login', () => {
    expect(isExplicitOrgScope('all')).toBe(true);
    expect(isExplicitOrgScope('30')).toBe(true);
    expect(isExplicitOrgScope(null)).toBe(false);
    expect(isExplicitOrgScope('mine')).toBe(false);
    expect(isExplicitOrgScope('abc')).toBe(false);
  });
});

describe('default scope helpers', () => {
  it('knows the default per login state', () => {
    expect(defaultOrgScope(true)).toEqual({ kind: 'mine' });
    expect(defaultOrgScope(false)).toEqual({ kind: 'all' });
    expect(isDefaultOrgScope({ kind: 'mine' }, true)).toBe(true);
    expect(isDefaultOrgScope({ kind: 'all' }, true)).toBe(false);
    expect(isDefaultOrgScope({ kind: 'all' }, false)).toBe(true);
    expect(isDefaultOrgScope({ kind: 'org', id: 3 }, false)).toBe(false);
  });

  it('maps scopes to select values', () => {
    expect(orgScopeValue({ kind: 'mine' })).toBe('mine');
    expect(orgScopeValue({ kind: 'all' })).toBe('all');
    expect(orgScopeValue({ kind: 'org', id: 7 })).toBe('7');
  });
});

describe('orgScopeParam', () => {
  it('drops the param for the default scope and sets it otherwise', () => {
    expect(orgScopeParam('mine', true)).toBeNull();
    expect(orgScopeParam('all', true)).toBe('all');
    expect(orgScopeParam('all', false)).toBeNull();
    expect(orgScopeParam('30', true)).toBe('30');
    expect(orgScopeParam('30', false)).toBe('30');
  });
});

describe('orgScopeRequest', () => {
  it('sends member orgs plus open signups for mine on upcoming', () => {
    expect(orgScopeRequest({ kind: 'mine' }, 'upcoming', [31, 30])).toEqual({
      organizations: [30, 31],
      openSignups: true,
    });
  });

  it('sends member orgs only for mine on archived', () => {
    expect(orgScopeRequest({ kind: 'mine' }, 'archived', [30])).toEqual({
      organizations: [30],
    });
  });

  it('sends an empty organization list for a user without memberships', () => {
    expect(orgScopeRequest({ kind: 'mine' }, 'upcoming', undefined)).toEqual({
      organizations: [],
      openSignups: true,
    });
    expect(orgScopeRequest({ kind: 'mine' }, 'archived', [])).toEqual({
      organizations: [],
    });
  });

  it('sends a single organization or nothing', () => {
    expect(orgScopeRequest({ kind: 'org', id: 5 }, 'upcoming', [30])).toEqual({
      organization: 5,
    });
    expect(orgScopeRequest({ kind: 'all' }, 'archived', [30])).toEqual({});
  });
});

describe('groupOrganizations', () => {
  const orgs = [
    { pk: 1, name: 'A' },
    { pk: 2, name: 'B' },
    { pk: null, name: 'Draft' },
    { pk: 3, name: 'C' },
  ];

  it('splits organizations by membership and keeps their order', () => {
    expect(groupOrganizations(orgs, [3, 1])).toEqual({
      yours: [orgs[0], orgs[3]],
      others: [orgs[1]],
    });
  });

  it('puts everything in others without memberships', () => {
    expect(groupOrganizations(orgs, undefined)).toEqual({
      yours: [],
      others: [orgs[0], orgs[1], orgs[3]],
    });
  });
});

describe('showsSignupsOpenBadge', () => {
  it('marks open-signup tournaments from orgs the user is not in', () => {
    expect(showsSignupsOpenBadge(tournament(31, true), [30])).toBe(true);
    expect(showsSignupsOpenBadge(tournament(null, true), [30])).toBe(true);
  });

  it('does not mark member-org or closed tournaments', () => {
    expect(showsSignupsOpenBadge(tournament(30, true), [30])).toBe(false);
    expect(showsSignupsOpenBadge(tournament(31, false), [30])).toBe(false);
    expect(
      showsSignupsOpenBadge({ ...tournament(31, false), signups_open: undefined }, [30]),
    ).toBe(false);
  });
});
