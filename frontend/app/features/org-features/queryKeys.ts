import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { TrackKey } from '~/features/standing/schemas';

type ViewerPk = number | null;
type Filters = object;

const CONTRIBUTIONS = 'org-contributions';
const PROMOTION = 'org-promotion';
const STANDING = 'org-standing';
const CONDUCT = 'org-conduct';

export const contributionsKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    [CONTRIBUTIONS, orgId, viewerPk] as const,
  leaderboard: (orgId: number, viewerPk: ViewerPk, period: string) =>
    [...contributionsKeys.all(orgId, viewerPk), 'leaderboard', period] as const,
  member: (
    orgId: number,
    viewerPk: ViewerPk,
    orgUserPk: number,
    period: string,
  ) =>
    [
      ...contributionsKeys.all(orgId, viewerPk),
      'member',
      orgUserPk,
      period,
    ] as const,
  pointValues: (orgId: number, viewerPk: ViewerPk) =>
    [...contributionsKeys.all(orgId, viewerPk), 'point-values'] as const,
  entries: (orgId: number, viewerPk: ViewerPk, filters: Filters) =>
    [...contributionsKeys.all(orgId, viewerPk), 'entries', filters] as const,
};

export const promotionKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    [PROMOTION, orgId, viewerPk] as const,
  templates: (orgId: number, viewerPk: ViewerPk) =>
    [...promotionKeys.all(orgId, viewerPk), 'templates'] as const,
  events: (orgId: number, viewerPk: ViewerPk) =>
    [...promotionKeys.all(orgId, viewerPk), 'events'] as const,
  candidates: (
    orgId: number,
    viewerPk: ViewerPk,
    eventId: number,
    filters: Filters,
  ) =>
    [
      ...promotionKeys.all(orgId, viewerPk),
      'candidates',
      eventId,
      filters,
    ] as const,
};

export const standingKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    [STANDING, orgId, viewerPk] as const,
  track: (orgId: number, viewerPk: ViewerPk, track: TrackKey) =>
    [...standingKeys.all(orgId, viewerPk), track] as const,
  leaderboard: (
    orgId: number,
    viewerPk: ViewerPk,
    track: TrackKey,
    metricKey: string,
    period: string,
  ) =>
    [
      ...standingKeys.track(orgId, viewerPk, track),
      'leaderboard',
      metricKey,
      period,
    ] as const,
};

export const conductKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    [CONDUCT, orgId, viewerPk] as const,
  member: (
    orgId: number,
    viewerPk: ViewerPk,
    orgUserPk: number,
    page: { limit: number; offset: number },
  ) => [...conductKeys.members(orgId, viewerPk), orgUserPk, page] as const,
  members: (orgId: number, viewerPk: ViewerPk) =>
    [...conductKeys.all(orgId, viewerPk), 'member'] as const,
  settings: (orgId: number, viewerPk: ViewerPk) =>
    [...conductKeys.all(orgId, viewerPk), 'settings'] as const,
  event: (orgId: number, viewerPk: ViewerPk, eventId: number) =>
    [...conductKeys.all(orgId, viewerPk), 'event', eventId] as const,
  attendance: (orgId: number, viewerPk: ViewerPk, eventId: number) =>
    [...conductKeys.event(orgId, viewerPk, eventId), 'attendance'] as const,
  forecast: (orgId: number, viewerPk: ViewerPk, eventId: number) =>
    [...conductKeys.event(orgId, viewerPk, eventId), 'forecast'] as const,
};

export async function invalidateContributionQueries(
  queryClient: QueryClient,
  orgId: number,
  viewerPk: ViewerPk,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: contributionsKeys.all(orgId, viewerPk),
    }),
    queryClient.invalidateQueries({
      queryKey: standingKeys.track(orgId, viewerPk, 'contribution'),
    }),
  ]);
}

export async function invalidateOrgContributionQueries(
  queryClient: QueryClient,
  orgId: number,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: [CONTRIBUTIONS, orgId] }),
    queryClient.invalidateQueries({
      queryKey: [STANDING, orgId],
      predicate: (query) => query.queryKey[3] === 'contribution',
    }),
  ]);
}

function startsWith(key: QueryKey, prefix: QueryKey): boolean {
  return (
    prefix.length <= key.length &&
    prefix.every((part, index) => key[index] === part)
  );
}

export async function invalidateConductQueries(
  queryClient: QueryClient,
  orgId?: number | null,
  options: { except?: QueryKey } = {},
): Promise<void> {
  const { except } = options;
  const scope = orgId == null ? [] : [orgId];
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: [CONDUCT, ...scope],
      predicate: except
        ? (query) => !startsWith(query.queryKey, except)
        : undefined,
    }),
    queryClient.invalidateQueries({
      queryKey: [STANDING, ...scope],
      predicate: (query) => query.queryKey[3] === 'conduct',
    }),
  ]);
}

export const orgFeaturesKey = (orgId: number) =>
  ['org-features', orgId] as const;

export function removeFeatureQueries(
  queryClient: QueryClient,
  orgId: number,
): void {
  queryClient.removeQueries({ queryKey: [CONTRIBUTIONS, orgId] });
  queryClient.removeQueries({ queryKey: [PROMOTION, orgId] });
  queryClient.removeQueries({ queryKey: [STANDING, orgId] });
  queryClient.removeQueries({ queryKey: [CONDUCT, orgId] });
  queryClient.removeQueries({ queryKey: orgFeaturesKey(orgId) });
}
