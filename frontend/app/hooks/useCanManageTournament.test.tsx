// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  useCanManageCurrentTournament,
  useCanManageTournament,
} from './useCanManageTournament';

const LEAGUE_PK = 9;
const ORG_PK = 8;
const tournament = { league_pk: LEAGUE_PK, organization_pk: ORG_PK };

function asUser(fields: Partial<UserType> | null) {
  useUserStore.setState({
    currentUser: fields
      ? ({ pk: 1, username: 'u', ...fields } as UserType)
      : null,
  } as never);
}

function can(t = tournament as Parameters<typeof useCanManageTournament>[0]) {
  return renderHook(() => useCanManageTournament(t)).result.current;
}

afterEach(() =>
  useUserStore.setState({ currentUser: null, tournament: null } as never),
);

describe('useCanManageTournament', () => {
  it.each([
    ['site staff', { is_staff: true }],
    ['superuser', { is_superuser: true }],
    ['org admin/owner', { admin_organization_ids: [ORG_PK] }],
    ['org staff', { staff_organization_ids: [ORG_PK] }],
    ['league admin', { admin_league_ids: [LEAGUE_PK] }],
    ['league staff', { staff_league_ids: [LEAGUE_PK] }],
  ])('grants %s', (_label, fields) => {
    asUser(fields as Partial<UserType>);
    expect(can()).toBe(true);
  });

  it.each([
    ['a plain user', {}],
    ['staff of another org', { staff_organization_ids: [99] }],
    ['staff of another league', { staff_league_ids: [99] }],
  ])('denies %s', (_label, fields) => {
    asUser(fields as Partial<UserType>);
    expect(can()).toBe(false);
  });

  it('denies anonymous viewers', () => {
    asUser(null);
    expect(can()).toBe(false);
  });

  it('grants event-org staff on a league-less tournament', () => {
    asUser({ staff_organization_ids: [ORG_PK] });
    expect(can({ league_pk: null, organization_pk: ORG_PK })).toBe(true);
  });

  it('denies league staff on a league-less tournament', () => {
    asUser({ staff_league_ids: [LEAGUE_PK] });
    expect(can({ league_pk: null, organization_pk: ORG_PK })).toBe(false);
  });

  it('reads the store tournament', () => {
    asUser({ staff_league_ids: [LEAGUE_PK] });
    useUserStore.setState({ tournament } as never);
    expect(
      renderHook(() => useCanManageCurrentTournament()).result.current,
    ).toBe(true);
  });
});
