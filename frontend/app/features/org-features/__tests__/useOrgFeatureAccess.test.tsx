// @vitest-environment jsdom
import { QueryClient } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { OrganizationSchema, type OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  contributionsKeys,
  orgFeaturesKey,
  promotionKeys,
  removeFeatureQueries,
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
};

function org(viewerPk: number | null): OrganizationType {
  return { pk: 7, name: 'Org', members_viewer_pk: viewerPk, can_view_members: true, ...allTrue } as OrganizationType;
}

const allFalseFlags = {
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: false,
  canViewContributors: false,
  canManageContributions: false,
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
  });

  it('keeps flags the backend sent', () => {
    const parsed = OrganizationSchema.parse({ name: 'Org', ...allTrue });
    expect(parsed.features).toEqual(['contributions', 'promotion']);
    expect(parsed.can_manage_contributions).toBe(true);
  });
});

describe('useOrgFeatureAccess', () => {
  beforeEach(() => setViewer(null));

  it('returns every flag false when the payload viewer is someone else', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(org(9)));
    expect(result.current).toEqual({ settled: false, viewerPk: 5, ...allFalseFlags });
  });

  it('returns every flag false for an undefined org', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(undefined));
    expect(result.current).toEqual({ settled: false, viewerPk: 5, ...allFalseFlags });
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
    });
  });

  it('settles for an anonymous viewer and an anonymous payload', () => {
    const { result } = renderHook(() =>
      useOrgFeatureAccess({ ...org(null), can_use_promotion: false } as OrganizationType),
    );
    expect(result.current.settled).toBe(true);
    expect(result.current.viewerPk).toBeNull();
    expect(result.current.canViewContributions).toBe(true);
    expect(result.current.canUsePromotion).toBe(false);
  });

  it('drops flags as soon as the viewer logs out', () => {
    setViewer(5);
    const { result } = renderHook(() => useOrgFeatureAccess(org(5)));
    expect(result.current.canManageContributions).toBe(true);
    act(() => setViewer(null));
    expect(result.current).toEqual({ settled: false, viewerPk: null, ...allFalseFlags });
  });
});

describe('removeFeatureQueries', () => {
  it('removes contributions and promotion queries for the org only', () => {
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

    removeFeatureQueries(qc, 7);

    const remaining = qc
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey);
    expect(remaining).toEqual(
      expect.arrayContaining([['organization', 7], orgFeaturesKey(7), contributionsKeys.leaderboard(8, 5, 'all')]),
    );
    expect(remaining).toHaveLength(3);
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
});
