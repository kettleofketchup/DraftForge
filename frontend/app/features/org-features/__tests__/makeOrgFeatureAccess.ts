import type { OrgFeatureAccess } from '../useOrgFeatureAccess';

export function makeOrgFeatureAccess(
  overrides: Partial<OrgFeatureAccess> = {},
): OrgFeatureAccess {
  return {
    settled: true,
    viewerPk: 1,
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
    ...overrides,
  };
}
