import type { ClaimStatus } from './schemas';

type ViewerPk = number | null;

export const claimKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    ['org-claims', orgId, viewerPk] as const,
  list: (orgId: number, viewerPk: ViewerPk, status: ClaimStatus) =>
    [...claimKeys.all(orgId, viewerPk), status] as const,
};
