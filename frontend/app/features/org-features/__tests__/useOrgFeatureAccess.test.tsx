// @vitest-environment jsdom
import { QueryClient } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  OrganizationSchema,
  type OrganizationType,
} from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  apiTokenKeys,
  conductKeys,
  contributionsKeys,
  orgFeaturesKey,
  promotionKeys,
  removeFeatureQueries,
  standingKeys,
} from '../queryKeys';
import { useOrgFeatureAccess } from '../useOrgFeatureAccess';

function setViewer(pk: number | null) {
  useUserStore.setState({
    currentUser: (pk == null ? {} : { pk, username: `u${pk}` }) as UserType,
  });
}

const allTrue = {
  features: ['contributions', 'promotion'],
  can_use_promotion: true,
  can_manage_promotion_templates: true,
  can_manage_promoters: true,
  can_view_contributions: true,
  can_view_contributors: true,
  can_manage_contributions: true,
  can_view_conduct: true,
  can_view_own_conduct: true,
  can_view_conduct_details: true,
  can_manage_conduct: true,
  standing_tracks: [
    {
      key: 'conduct',
      label: 'Conduct',
      metrics: [
        {
          key: 'show_rate',
          label: 'Show rate',
          format: 'percent',
          periodic: false,
          default: true,
        },
      ],
      can_view_rows: true,
      can_view_own: true,
      board_open: true,
      can_manage: true,
      can_moderate: false,
      own_private: false,
    },
  ],
};

function org(viewerPk: number | null): OrganizationType {
  return {
    pk: 7,
    name: 'Org',
    members_viewer_pk: viewerPk,
    can_view_members: true,
    ...allTrue,
  } as OrganizationType;
}

const allFalseFlags = {
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: false,
  canViewContributors: false,
  canManageContributions: false,
  canViewConduct: false,
  canViewOwnConduct: false,
  canViewConductDetails: false,
  canManageConduct: false,
  mmrSyncEnabled: false,
  canUseMmrSync: false,
  promotionEnabled: false,
  canUseApiTokens: false,
  standingTracks: [],
};

describe('OrganizationSchema feature fields', () => {
  it('defaults features and flags when absent', () => {
    const parsed = OrganizationSchema.parse({ name: 'Org' });
    expect(parsed.features).toEqual([]);
    expect(parsed.can_use_promotion).toBe(false);
    expect(parsed.can_manage_promotion_templates).toBe(false);
    expect(parsed.can_manage_promoters).toBe(false);
    expect(parsed.can_view_contributions).toBe(false);
    expect(parsed.can_view_contributors).toBe(false);
    expect(parsed.can_manage_contributions).toBe(false);
    expect(parsed.can_view_conduct).toBe(false);
    expect(parsed.can_view_own_conduct).toBe(false);
    expect(parsed.can_view_conduct_details).toBe(false);
    expect(parsed.can_manage_conduct).toBe(false);
    expect(parsed.standing_tracks).toEqual([]);
  });

  it('keeps flags the backend sent', () => {
    const parsed = OrganizationSchema.parse({ name: 'Org', ...allTrue });
    expect(parsed.features).toEqual(['contributions', 'promotion']);
    expect(parsed.can_manage_contributions).toBe(true);
    expect(parsed.can_view_conduct).toBe(true);
    expect(parsed.can_view_own_conduct).toBe(true);
    expect(parsed.can_view_conduct_details).toBe(true);
    expect(parsed.can_manage_conduct).toBe(true);
    expect(parsed.standing_tracks.map((t) => t.key)).toEqual(['conduct']);
  });

  it('rejects a malformed standing track', () => {
    const result = OrganizationSchema.safeParse({
      name: 'Org',
      standing_tracks: [{ key: 'karma', label: 'Karma', metrics: [] }],
    });
    expect(result.success).toBe(false);
  });
});

describe('useOrgFeatureAccess', () => {
  beforeEach(() => setViewer(null));

  it('returns every flag false when the payload viewer is someone else', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(org(9)));
    expect(result.current).toEqual({
      settled: false,
      viewerPk: 5,
      ...allFalseFlags,
    });
  });

  it('returns every flag false for an undefined org', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(undefined));
    expect(result.current).toEqual({
      settled: false,
      viewerPk: 5,
      ...allFalseFlags,
    });
  });

  it('returns the payload flags once settled for the current viewer', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(org(5)));
    expect(result.current).toEqual({
      settled: true,
      viewerPk: 5,
      canUsePromotion: true,
      canManageTemplates: true,
      canManagePromoters: true,
      canViewContributions: true,
      canViewContributors: true,
      canManageContributions: true,
      canViewConduct: true,
      canViewOwnConduct: true,
      canViewConductDetails: true,
      canManageConduct: true,
      mmrSyncEnabled: false,
      canUseMmrSync: false,
      promotionEnabled: true,
      canUseApiTokens: false,
      standingTracks: allTrue.standing_tracks,
    });
  });

  it('settles for an anonymous viewer and an anonymous payload', () => {
    const { result } = renderHook(() =>
      useOrgFeatureAccess({
        ...org(null),
        can_use_promotion: false,
      } as OrganizationType),
    );
    expect(result.current.settled).toBe(true);
    expect(result.current.viewerPk).toBeNull();
    expect(result.current.canViewContributions).toBe(true);
    expect(result.current.canUsePromotion).toBe(false);
    expect(result.current.standingTracks).toEqual(allTrue.standing_tracks);
  });

  it('drops flags as soon as the viewer logs out', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(org(5)));
    expect(result.current.canManageContributions).toBe(true);
    act(() => setViewer(null));
    expect(result.current).toEqual({
      settled: false,
      viewerPk: null,
      ...allFalseFlags,
    });
  });
});

describe('useOrgFeatureAccess mmr sync', () => {
  function mmrOrg(features: string[], extra: Partial<OrganizationType> = {}) {
    return {
      ...org(5),
      features,
      admin_ids: [],
      staff_ids: [],
      ...extra,
    } as OrganizationType;
  }

  function setUser(isStaff = false) {
    useUserStore.setState({
      currentUser: { pk: 5, username: 'u5', is_staff: isStaff } as UserType,
    });
  }

  it('lets org admins use it once the feature is on', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(mmrOrg(['mmr_sync'], { admin_ids: [5] })),
    );
    expect(result.current.mmrSyncEnabled).toBe(true);
    expect(result.current.canUseMmrSync).toBe(true);
  });

  it('hides it from org admins while the feature is locked', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(mmrOrg([], { admin_ids: [5] })),
    );
    expect(result.current.canUseMmrSync).toBe(false);
  });

  it('hides it from org staff who are not admins', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(mmrOrg(['mmr_sync'], { staff_ids: [5] })),
    );
    expect(result.current.canUseMmrSync).toBe(false);
  });

  it('hides it from plain members', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(mmrOrg(['mmr_sync'])),
    );
    expect(result.current.canUseMmrSync).toBe(false);
  });

  it('shows it to a site admin even while locked', () => {
    setUser(true);
    const { result } = renderHook(() => useOrgFeatureAccess(mmrOrg([])));
    expect(result.current.mmrSyncEnabled).toBe(false);
    expect(result.current.canUseMmrSync).toBe(true);
  });
});

describe('useOrgFeatureAccess API tokens', () => {
  function tokenOrg(features: string[], extra: Partial<OrganizationType> = {}) {
    return {
      ...org(5),
      features,
      admin_ids: [],
      staff_ids: [],
      ...extra,
    } as OrganizationType;
  }

  function setUser(isStaff = false) {
    useUserStore.setState({
      currentUser: { pk: 5, username: 'u5', is_staff: isStaff } as UserType,
    });
  }

  it.each([['promotion'], ['mmr_sync']])(
    'lets org admins manage tokens when %s is unlocked',
    (feature) => {
      setUser();
      const { result } = renderHook(() =>
        useOrgFeatureAccess(tokenOrg([feature], { admin_ids: [5] })),
      );
      expect(result.current.canUseApiTokens).toBe(true);
    },
  );

  it('does not let the contributions feature alone unlock tokens', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(tokenOrg(['contributions'], { admin_ids: [5] })),
    );
    expect(result.current.canUseApiTokens).toBe(false);
  });

  it('reports which token features are unlocked', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(
        tokenOrg(['promotion', 'contributions'], { admin_ids: [5] }),
      ),
    );
    expect(result.current.promotionEnabled).toBe(true);
    expect(result.current).not.toHaveProperty('contributionsEnabled');
    expect(result.current.mmrSyncEnabled).toBe(false);
    expect(result.current.canUseMmrSync).toBe(false);
  });

  it('hides tokens from org admins while no token feature is unlocked', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(tokenOrg(['conduct'], { admin_ids: [5] })),
    );
    expect(result.current.canUseApiTokens).toBe(false);
  });

  it('hides tokens from org staff who are not admins', () => {
    setUser();
    const { result } = renderHook(() =>
      useOrgFeatureAccess(tokenOrg(['promotion'], { staff_ids: [5] })),
    );
    expect(result.current.canUseApiTokens).toBe(false);
  });

  it('shows tokens to a site admin even while locked', () => {
    setUser(true);
    const { result } = renderHook(() => useOrgFeatureAccess(tokenOrg([])));
    expect(result.current.canUseApiTokens).toBe(true);
  });
});

describe('removeFeatureQueries', () => {
  it('removes contributions, promotion and feature-row queries for the org only', () => {
    const qc = new QueryClient();
    qc.setQueryData(contributionsKeys.leaderboard(7, 5, 'all'), ['row']);
    qc.setQueryData(contributionsKeys.member(7, 5, 11, 'all'), ['entry']);
    qc.setQueryData(contributionsKeys.pointValues(7, 5), ['pv']);
    qc.setQueryData(contributionsKeys.entries(7, 5, { kind: 'manual' }), ['e']);
    qc.setQueryData(promotionKeys.templates(7, 5), ['t']);
    qc.setQueryData(promotionKeys.events(7, 5), ['ev']);
    qc.setQueryData(promotionKeys.candidates(7, 5, 3, { n: 3 }), ['c']);
    qc.setQueryData(['organization', 7], { pk: 7 });
    qc.setQueryData(orgFeaturesKey(7), ['f']);
    qc.setQueryData(contributionsKeys.leaderboard(8, 5, 'all'), ['other']);
    qc.setQueryData(
      standingKeys.leaderboard(7, 5, 'conduct', 'show_rate', 'current'),
      ['s'],
    );
    qc.setQueryData(conductKeys.member(7, 5, 11, { limit: 20, offset: 0 }), [
      'h',
    ]);
    qc.setQueryData(conductKeys.settings(7, 5), ['cs']);
    qc.setQueryData(standingKeys.track(8, 5, 'conduct'), ['other-s']);
    qc.setQueryData(conductKeys.settings(8, 5), ['other-c']);
    qc.setQueryData(apiTokenKeys.tokens(7, 5), ['tok']);

    removeFeatureQueries(qc, 7);

    const remaining = qc
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey);
    expect(remaining).toEqual(
      expect.arrayContaining([
        ['organization', 7],
        contributionsKeys.leaderboard(8, 5, 'all'),
        standingKeys.track(8, 5, 'conduct'),
        conductKeys.settings(8, 5),
      ]),
    );
    expect(remaining).toHaveLength(4);
  });

  it('nests every contributions and promotion key under its all() prefix', () => {
    const cAll = contributionsKeys.all(7, 5);
    const pAll = promotionKeys.all(7, 5);
    expect(cAll.slice(0, 2)).toEqual(['org-contributions', 7]);
    expect(pAll.slice(0, 2)).toEqual(['org-promotion', 7]);
    for (const key of [
      contributionsKeys.leaderboard(7, 5, 'month'),
      contributionsKeys.member(7, 5, 1, 'month'),
      contributionsKeys.pointValues(7, 5),
      contributionsKeys.entries(7, 5, {}),
    ]) {
      expect(key.slice(0, cAll.length)).toEqual(cAll);
    }
    for (const key of [
      promotionKeys.templates(7, 5),
      promotionKeys.events(7, 5),
      promotionKeys.candidates(7, 5, 1, {}),
    ]) {
      expect(key.slice(0, pAll.length)).toEqual(pAll);
    }
  });

  it('nests every standing and conduct key under its all() prefix', () => {
    const sAll = standingKeys.all(7, 5);
    const cAll = conductKeys.all(7, 5);
    expect(sAll).toEqual(['org-standing', 7, 5]);
    expect(cAll).toEqual(['org-conduct', 7, 5]);
    const track = standingKeys.track(7, 5, 'contribution');
    expect(track.slice(0, sAll.length)).toEqual(sAll);
    const board = standingKeys.leaderboard(
      7,
      5,
      'contribution',
      'points',
      '2026-10',
    );
    expect(board.slice(0, track.length)).toEqual(track);
    for (const key of [
      conductKeys.member(7, 5, 1, { limit: 20, offset: 0 }),
      conductKeys.settings(7, 5),
    ]) {
      expect(key.slice(0, cAll.length)).toEqual(cAll);
    }
  });
});
