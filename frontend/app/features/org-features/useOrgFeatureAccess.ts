import type { OrganizationType } from '~/components/organization/schemas';
import type { TrackInfo } from '~/features/standing/schemas';
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
  /** A leadership entry exists in `standing_tracks`. */
  leadershipUnlocked: boolean;
  canManageLeadership: boolean;
  /** The viewer is an org member, so the rater endpoints answer. */
  leadershipMember: boolean;
  /** The member endpoint answers for other captains (admin, or non-staff on a public board). */
  leadershipCanOpenOthers: boolean;
  standingTracks: TrackInfo[];
}

const NO_TRACKS: TrackInfo[] = [];

export function useOrgFeatureAccess(
  org: OrganizationType | undefined,
): OrgFeatureAccess {
  const viewerPk = useUserStore((s) => s.currentUser?.pk ?? null);
  const settled =
    org?.members_viewer_pk !== undefined && org.members_viewer_pk === viewerPk;
  const flag = (value: boolean | undefined): boolean =>
    settled && value === true;
  const leadership = settled
    ? org?.standing_tracks?.find((track) => track.key === 'leadership')
    : undefined;
  const canManageLeadership = leadership?.can_manage === true;
  const viewerIsOrgStaff =
    viewerPk != null && (org?.staff ?? []).some((user) => user.pk === viewerPk);
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
    leadershipUnlocked: leadership !== undefined,
    canManageLeadership,
    leadershipMember: leadership?.can_view_own === true,
    leadershipCanOpenOthers:
      canManageLeadership ||
      (leadership?.can_view_rows === true && !viewerIsOrgStaff),
    standingTracks: (settled && org?.standing_tracks) || NO_TRACKS,
  };
}
