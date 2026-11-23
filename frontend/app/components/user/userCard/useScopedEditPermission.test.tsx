// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { type EditUserScope, useScopedEditPermission } from './editUserSchema';

const ORG_PK = 3;
const league = {
  pk: 10,
  name: 'L',
  organization: { pk: ORG_PK },
} as unknown as LeagueType;
const leagueScope: EditUserScope = { kind: 'league', league };

function asUser(fields: Partial<UserType>) {
  useUserStore.setState({
    currentUser: { pk: 1, username: 'u', ...fields } as UserType,
  });
}

function canEdit(scope: EditUserScope) {
  return renderHook(() => useScopedEditPermission(scope)).result.current;
}

afterEach(() => useUserStore.setState({ currentUser: null } as never));

describe('useScopedEditPermission league scope', () => {
  it('grants staff of the parent org (backend update_org_user gate)', () => {
    asUser({ staff_organization_ids: [ORG_PK] });
    expect(canEdit(leagueScope)).toBe(true);
  });

  it('grants admins of the parent org', () => {
    asUser({ admin_organization_ids: [ORG_PK] });
    expect(canEdit(leagueScope)).toBe(true);
  });

  it('resolves the org from scope.orgId when the league carries none', () => {
    asUser({ staff_organization_ids: [ORG_PK] });
    expect(
      canEdit({
        kind: 'league',
        league: { ...league, organization: null },
        orgId: ORG_PK,
      }),
    ).toBe(true);
  });

  it('denies staff of a different org', () => {
    asUser({ staff_organization_ids: [99] });
    expect(canEdit(leagueScope)).toBe(false);
  });

  it('denies league-only admins, whom the org endpoint would 403', () => {
    asUser({ admin_league_ids: [league.pk as number] });
    expect(canEdit(leagueScope)).toBe(false);
  });

  it('grants site staff', () => {
    asUser({ is_staff: true });
    expect(canEdit(leagueScope)).toBe(true);
  });
});
