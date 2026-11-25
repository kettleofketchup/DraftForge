import type { MmrQueueStatus } from './schemas';

export type MmrScope = { org: number } | { league: number };
type ViewerPk = number | null;

const ROOT = 'mmr-requests';

export const mmrKeys = {
  all: [ROOT] as const,
  summary: (userPk: number, viewerPk: ViewerPk) =>
    [ROOT, 'summary', userPk, viewerPk] as const,
  mine: (viewerPk: ViewerPk) => [ROOT, 'mine', viewerPk] as const,
  scope: (scope: MmrScope, viewerPk: ViewerPk) =>
    [ROOT, scope, viewerPk] as const,
  queue: (scope: MmrScope, viewerPk: ViewerPk, status: MmrQueueStatus) =>
    [...mmrKeys.scope(scope, viewerPk), 'queue', status] as const,
  pendingCount: (scope: MmrScope, viewerPk: ViewerPk) =>
    [...mmrKeys.scope(scope, viewerPk), 'pending-count'] as const,
};
