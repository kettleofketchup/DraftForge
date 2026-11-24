import type { OrganizationType } from '~/components/organization/schemas';
import type { TrackInfo } from '~/features/standing/schemas';
import { useIsOrganizationAdmin, useIsSuperuser } from '~/hooks/usePermissions';
import { useUserStore } from '~/store/userStore';

export interface OrgFeatureAccess {
  /** The flags were computed for the signed-in viewer; every flag is false until then. */
  settled: boolean;
  viewerPk: number | null;
  canUsePromotion: boolean;
  canManageTemplates: boolean;
  canManagePromoters: boolean;
  canViewContributions: boolean;
  canViewContributors: boolean;
  canManageContributions: boolean;
  canViewConduct: boolean;
  canViewOwnConduct: boolean;
  canViewConductDetails: boolean;
  canManageConduct: boolean;
  /** The mmr_sync feature is unlocked for this org. */
  mmrSyncEnabled: boolean;
  /** Org admins while mmr_sync is unlocked, or a site admin. */
  canUseMmrSync: boolean;
  standingTracks: TrackInfo[];
}

const NO_TRACKS: TrackInfo[] = [];

export function useOrgFeatureAccess(
  org: OrganizationType | undefined,
): OrgFeatureAccess {
  const viewerPk = useUserStore((s) => s.currentUser?.pk ?? null);
  const isOrgAdmin = useIsOrganizationAdmin(org);
  const isSiteAdmin = useIsSuperuser();
  const settled =
    org?.members_viewer_pk !== undefined && org.members_viewer_pk === viewerPk;
  const flag = (value: boolean | undefined): boolean =>
    settled && value === true;
  const mmrSyncEnabled = flag(org?.features?.includes('mmr_sync'));
  return {
    settled,
    viewerPk,
    canUsePromotion: flag(org?.can_use_promotion),
    canManageTemplates: flag(org?.can_manage_promotion_templates),
    canManagePromoters: flag(org?.can_manage_promoters),
    canViewContributions: flag(org?.can_view_contributions),
    canViewContributors: flag(org?.can_view_contributors),
    canManageContributions: flag(org?.can_manage_contributions),
    canViewConduct: flag(org?.can_view_conduct),
    canViewOwnConduct: flag(org?.can_view_own_conduct),
    canViewConductDetails: flag(org?.can_view_conduct_details),
    canManageConduct: flag(org?.can_manage_conduct),
    mmrSyncEnabled,
    canUseMmrSync: settled && isOrgAdmin && (isSiteAdmin || mmrSyncEnabled),
    standingTracks: (settled && org?.standing_tracks) || NO_TRACKS,
  };
}
