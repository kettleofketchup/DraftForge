import { describe, it, expect } from 'vitest';
import { scopeToContext, type EditUserScope } from './editUserSchema';
import type { LeagueType } from '~/components/league/schemas';

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
