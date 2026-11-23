// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  type EditUserScope,
  useScopedEditMode,
  useScopedEditPermission,
  useTournamentEditScope,
} from './editUserSchema';

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

afterEach(() =>
  useUserStore.setState({ currentUser: null, tournament: null } as never),
);

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

describe('useScopedEditMode league staff in their tournament', () => {
  const mode = (scope: EditUserScope) =>
    renderHook(() => useScopedEditMode(scope)).result.current;

  it('gives league staff MMR-only edits with a tournament', () => {
    asUser({ staff_league_ids: [10] });
    expect(mode({ ...leagueScope, tournamentId: 5 })).toBe('mmr');
  });

  it('gives league admins MMR-only edits with a tournament', () => {
    asUser({ admin_league_ids: [10] });
    expect(mode({ ...leagueScope, tournamentId: 5 })).toBe('mmr');
  });

  it('gives league staff nothing without a tournament', () => {
    asUser({ staff_league_ids: [10] });
    expect(mode(leagueScope)).toBeNull();
  });

  it('keeps full edits for org staff', () => {
    asUser({ staff_organization_ids: [ORG_PK] });
    expect(mode({ ...leagueScope, tournamentId: 5 })).toBe('full');
  });
});

describe('useTournamentEditScope', () => {
  const scoped = (userPk: number) =>
    renderHook(() => useTournamentEditScope(leagueScope, userPk)).result
      .current;

  it('adds the store tournament for one of its players', () => {
    useUserStore.setState({
      tournament: { pk: 5, league_pk: 10, users: [{ pk: 42 }] },
    } as never);
    expect(scoped(42)).toMatchObject({ kind: 'league', tournamentId: 5 });
  });

  it('leaves the scope alone for a player outside the tournament', () => {
    useUserStore.setState({
      tournament: { pk: 5, league_pk: 10, users: [{ pk: 42 }] },
    } as never);
    expect(scoped(7)).not.toHaveProperty('tournamentId');
  });

  it('leaves the scope alone when the tournament is in another league', () => {
    useUserStore.setState({
      tournament: { pk: 5, league_pk: 11, users: [{ pk: 42 }] },
    } as never);
    expect(scoped(42)).not.toHaveProperty('tournamentId');
  });
});
