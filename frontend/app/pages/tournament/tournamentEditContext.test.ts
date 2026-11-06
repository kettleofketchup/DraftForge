import { afterEach, describe, expect, it } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { tournamentEditContext } from './tournamentEditContext';

describe('tournamentEditContext', () => {
  afterEach(() => {
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({ currentLeague: null });
  });

  it('null/undefined tournament -> both undefined', () => {
    const empty = { organizationId: undefined, leagueId: undefined };
    expect(tournamentEditContext(null)).toEqual(empty);
    expect(tournamentEditContext(undefined)).toEqual(empty);
  });

  it('null org/league pks -> both undefined', () => {
    expect(tournamentEditContext({ organization_pk: null, league_pk: null })).toEqual({
      organizationId: undefined,
      leagueId: undefined,
    });
  });

  it('returns the tournament pks', () => {
    expect(tournamentEditContext({ organization_pk: 8, league_pk: 8 })).toEqual({
      organizationId: 8,
      leagueId: 8,
    });
  });

  it('never falls back to the store org/league', () => {
    useOrgStore.setState({ currentOrg: { pk: 9, name: 'Stale' } as OrganizationType });
    useLeagueStore.setState({ currentLeague: { pk: 9, name: 'Stale' } as LeagueType });
    expect(tournamentEditContext({ organization_pk: null }).organizationId).toBeUndefined();
    expect(tournamentEditContext({ organization_pk: null }).leagueId).toBeUndefined();
    expect(tournamentEditContext({ organization_pk: 8 }).organizationId).toBe(8);
  });
});
