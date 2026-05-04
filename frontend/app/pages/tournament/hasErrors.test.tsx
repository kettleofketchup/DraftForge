import { describe, it, expect } from 'vitest';
import { deriveEditScope } from './hasErrors';

import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';

describe('deriveEditScope', () => {
  const org: OrganizationType = { pk: 7, name: 'Events Test Org' } as OrganizationType;
  const league: LeagueType = { pk: 7, name: 'Events Test League', organization: org } as LeagueType;

  it('returns league scope when a league is present', () => {
    expect(deriveEditScope({ league, currentOrg: org })).toEqual({
      kind: 'league',
      league,
    });
  });

  it('returns org scope when only an org is present (the #195 case)', () => {
    expect(deriveEditScope({ league: null, currentOrg: org })).toEqual({
      kind: 'org',
      organization: org,
    });
  });

  it('returns global scope when neither org nor league is loaded', () => {
    expect(deriveEditScope({ league: null, currentOrg: null })).toEqual({
      kind: 'global',
    });
  });

  it('prefers league when both are present (league > org > global)', () => {
    expect(deriveEditScope({ league, currentOrg: org })).toEqual({
      kind: 'league',
      league,
    });
  });
});
