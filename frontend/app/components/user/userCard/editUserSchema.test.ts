import { describe, it, expect } from 'vitest';
import { scopeToContext, resolveOrgUserLink, resolveEditScope, type EditUserScope } from './editUserSchema';
import type { LeagueType } from '~/components/league/schemas';
import type { UserEntry } from '~/store/userCacheTypes';
import type { OrganizationType } from '~/components/organization/schemas';

const league = { pk: 7, name: 'L' } as LeagueType;

describe('scopeToContext org-id chain', () => {
  it('prefers scope.orgId for league scope', () => {
    const scope: EditUserScope = { kind: 'league', league, orgId: 42 };
    expect(scopeToContext(scope)).toEqual({ orgId: 42 });
  });

  it('falls back to league.organization.pk when orgId absent', () => {
    const scope: EditUserScope = {
      kind: 'league',
      league: { pk: 7, name: 'L', organization: { pk: 9 } } as LeagueType,
    };
    expect(scopeToContext(scope)).toEqual({ orgId: 9 });
  });
});

const org = { pk: 2, name: 'Org' } as OrganizationType;
const lg = { pk: 5, name: 'League' } as LeagueType;

// Minimal UserEntry-shaped object (isUserEntry checks `'orgData' in user`).
function entry(over: Partial<UserEntry> = {}): UserEntry {
  return {
    pk: 1, username: 'u', orgData: {}, leagueData: {}, _fetchedAt: 0, ...over,
  } as UserEntry;
}

describe('resolveOrgUserLink', () => {
  it('returns the flat orgUserPk when present', () => {
    expect(resolveOrgUserLink({ orgUserPk: 110 }, { organizationId: 2 })).toBe(110);
  });

  it('falls back to orgData[orgId].id for a UserEntry without a flat field', () => {
    const u = entry({ orgData: { 2: { id: 110, mmr: 0, _fetchedAt: 0 } } });
    expect(resolveOrgUserLink(u, { organizationId: 2 })).toBe(110);
  });

  it('falls back to leagueData[leagueId].id', () => {
    const u = entry({ leagueData: { 5: { id: 111, mmr: 0, _fetchedAt: 0 } } });
    expect(resolveOrgUserLink(u, { leagueId: 5 })).toBe(111);
  });

  it('returns undefined for a plain user with no link', () => {
    expect(resolveOrgUserLink({ username: 'u' } as never, {})).toBeUndefined();
  });
});

describe('resolveEditScope', () => {
  it('no link -> global', () => {
    expect(
      resolveEditScope({ username: 'u' } as never, {
        organizationId: 2, leagueId: 5, currentOrg: org, currentLeague: lg,
      }),
    ).toEqual({ kind: 'global' });
  });

  it('flat link + leagueId matches currentLeague -> league with deterministic orgId', () => {
    expect(
      resolveEditScope({ orgUserPk: 110 }, {
        organizationId: 2, leagueId: 5, currentOrg: org, currentLeague: lg,
      }),
    ).toEqual({ kind: 'league', league: lg, orgId: 2 });
  });

  it('flat link + currentLeague stale/absent + currentOrg present -> org', () => {
    expect(
      resolveEditScope({ orgUserPk: 110 }, {
        organizationId: 2, leagueId: 5, currentOrg: org, currentLeague: null,
      }),
    ).toEqual({ kind: 'org', organization: org });
  });

  it('flat link + neither store loaded -> global (safe degrade)', () => {
    expect(
      resolveEditScope({ orgUserPk: 110 }, {
        organizationId: 2, leagueId: 5, currentOrg: null, currentLeague: null,
      }),
    ).toEqual({ kind: 'global' });
  });

  it('UserEntry orgData-only link -> org', () => {
    const u = entry({ orgData: { 2: { id: 110, mmr: 0, _fetchedAt: 0 } } });
    expect(
      resolveEditScope(u, { organizationId: 2, currentOrg: org, currentLeague: null }),
    ).toEqual({ kind: 'org', organization: org });
  });

  it('link present but MMR is 0 -> still scope-aware (gate keys on id, not mmr)', () => {
    const u = entry({ orgData: { 2: { id: 110, mmr: 0, _fetchedAt: 0 } } });
    expect(
      resolveEditScope(u, {
        organizationId: 2, leagueId: 5, currentOrg: org, currentLeague: lg,
      }),
    ).toEqual({ kind: 'league', league: lg, orgId: 2 });
  });

  it('/users invariant: link in orgData but NO org/league context + stale currentOrg -> global', () => {
    const u = entry({ orgData: { 2: { id: 110, mmr: 0, _fetchedAt: 0 } } });
    expect(
      resolveEditScope(u, { currentOrg: org, currentLeague: null }),
    ).toEqual({ kind: 'global' });
  });
});
