import type { QueryClient } from '@tanstack/react-query';

type ViewerPk = number | null;
type Filters = Record<string, unknown>;

const CONTRIBUTIONS = 'org-contributions';
const PROMOTION = 'org-promotion';

export const contributionsKeys = {
  all: (orgId: number, viewerPk: ViewerPk) => [CONTRIBUTIONS, orgId, viewerPk] as const,
  leaderboard: (orgId: number, viewerPk: ViewerPk, period: string) =>
    [...contributionsKeys.all(orgId, viewerPk), 'leaderboard', period] as const,
  member: (orgId: number, viewerPk: ViewerPk, orgUserPk: number, period: string) =>
    [...contributionsKeys.all(orgId, viewerPk), 'member', orgUserPk, period] as const,
  pointValues: (orgId: number, viewerPk: ViewerPk) =>
    [...contributionsKeys.all(orgId, viewerPk), 'point-values'] as const,
  entries: (orgId: number, viewerPk: ViewerPk, filters: Filters) =>
    [...contributionsKeys.all(orgId, viewerPk), 'entries', filters] as const,
};

export const promotionKeys = {
  all: (orgId: number, viewerPk: ViewerPk) => [PROMOTION, orgId, viewerPk] as const,
  templates: (orgId: number, viewerPk: ViewerPk) =>
    [...promotionKeys.all(orgId, viewerPk), 'templates'] as const,
  events: (orgId: number, viewerPk: ViewerPk) =>
    [...promotionKeys.all(orgId, viewerPk), 'events'] as const,
  candidates: (orgId: number, viewerPk: ViewerPk, eventId: number, filters: Filters) =>
    [...promotionKeys.all(orgId, viewerPk), 'candidates', eventId, filters] as const,
};

export const orgFeaturesKey = (orgId: number) => ['org-features', orgId] as const;

export function removeFeatureQueries(queryClient: QueryClient, orgId: number): void {
  queryClient.removeQueries({ queryKey: [CONTRIBUTIONS, orgId] });
  queryClient.removeQueries({ queryKey: [PROMOTION, orgId] });
}
