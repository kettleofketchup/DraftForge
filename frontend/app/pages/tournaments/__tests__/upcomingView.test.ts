import { describe, expect, it } from 'vitest';
import type { TournamentType } from '~/components/tournament/types';
import { coerceTab, resolveUpcomingView } from '../upcomingView';

function tournament(pk: number, orgId: number | null): TournamentType {
  return {
    pk,
    name: `T${pk}`,
    date_played: '2026-11-20T18:00:00Z',
    state: 'future',
    league: {
      pk: 1,
      name: 'League',
      organization_name: 'Org',
      organization_id: orgId,
      organization_logo: null,
    },
  } as TournamentType;
}

const BASE = {
  membershipPending: false,
  isLoggedIn: true,
  memberOrgIds: [30] as number[] | undefined,
  orgOrLeagueFilter: false,
};

describe('coerceTab', () => {
  it('falls back to upcoming for anything but archived', () => {
    expect(coerceTab('bogus')).toBe('upcoming');
    expect(coerceTab(null)).toBe('upcoming');
    expect(coerceTab(undefined)).toBe('upcoming');
    expect(coerceTab('upcoming')).toBe('upcoming');
    expect(coerceTab('archived')).toBe('archived');
  });
});

describe('resolveUpcomingView', () => {
  it('keeps the skeleton while membership is pending even with data', () => {
    const view = resolveUpcomingView({
      ...BASE,
      data: [tournament(1, 30)],
      membershipPending: true,
    });
    expect(view).toEqual({ kind: 'skeleton' });
  });

  it('shows the skeleton while data is undefined', () => {
    expect(resolveUpcomingView({ ...BASE, data: undefined })).toEqual({ kind: 'skeleton' });
  });

  it('renders flat when the refetch settled without membership ids', () => {
    const data = [tournament(1, 30)];
    const view = resolveUpcomingView({ ...BASE, data, memberOrgIds: undefined });
    expect(view).toEqual({ kind: 'flat', items: data });
  });

  it('renders empty for a member with no data, never tiers', () => {
    expect(resolveUpcomingView({ ...BASE, data: [] })).toEqual({ kind: 'empty' });
  });

  it('puts other-org tournaments in others with an empty yours tier', () => {
    const view = resolveUpcomingView({ ...BASE, data: [tournament(1, 31)] });
    expect(view.kind).toBe('tiers');
    if (view.kind !== 'tiers') return;
    expect(view.yours).toEqual([]);
    expect(view.others).toHaveLength(1);
  });

  it('leaves others empty when every tournament is in a member org', () => {
    const view = resolveUpcomingView({ ...BASE, data: [tournament(1, 30)] });
    expect(view.kind).toBe('tiers');
    if (view.kind !== 'tiers') return;
    expect(view.yours).toHaveLength(1);
    expect(view.others).toEqual([]);
  });

  it('renders flat when logged out', () => {
    const data = [tournament(1, 30)];
    const view = resolveUpcomingView({ ...BASE, data, isLoggedIn: false });
    expect(view).toEqual({ kind: 'flat', items: data });
  });

  it('renders flat when an org or league filter is set', () => {
    const data = [tournament(1, 30)];
    const view = resolveUpcomingView({ ...BASE, data, orgOrLeagueFilter: true });
    expect(view).toEqual({ kind: 'flat', items: data });
  });

  it('keeps tiers for a member with only a search', () => {
    const view = resolveUpcomingView({
      ...BASE,
      data: [tournament(1, 30), tournament(2, 31)],
      orgOrLeagueFilter: false,
    });
    expect(view.kind).toBe('tiers');
  });

  it('renders flat for a logged-in user with no memberships', () => {
    const data = [tournament(1, 30)];
    const view = resolveUpcomingView({ ...BASE, data, memberOrgIds: [] });
    expect(view).toEqual({ kind: 'flat', items: data });
  });
});
