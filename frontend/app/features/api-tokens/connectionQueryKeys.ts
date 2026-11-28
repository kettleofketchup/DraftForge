import { apiTokenKeys } from '~/features/org-features';
import type { DeliveryState } from './connectionSchemas';

type ViewerPk = number | null;

/** Under the api-token feature scope, so feature-loss cleanup removes them too. Never holds secrets. */
export const connectionKeys = {
  all: (orgId: number, viewerPk: ViewerPk) =>
    [...apiTokenKeys.all(orgId, viewerPk), 'connections'] as const,
  list: (orgId: number, viewerPk: ViewerPk) =>
    [...connectionKeys.all(orgId, viewerPk), 'list'] as const,
  detail: (orgId: number, viewerPk: ViewerPk, connectionId: number) =>
    [...connectionKeys.all(orgId, viewerPk), 'detail', connectionId] as const,
  runs: (orgId: number, viewerPk: ViewerPk, connectionId: number) =>
    [...connectionKeys.detail(orgId, viewerPk, connectionId), 'runs'] as const,
  run: (
    orgId: number,
    viewerPk: ViewerPk,
    connectionId: number,
    runId: string,
  ) =>
    [
      ...connectionKeys.detail(orgId, viewerPk, connectionId),
      'run',
      runId,
    ] as const,
  deliveries: (
    orgId: number,
    viewerPk: ViewerPk,
    connectionId: number,
    state: DeliveryState | null,
  ) =>
    [
      ...connectionKeys.detail(orgId, viewerPk, connectionId),
      'deliveries',
      state,
    ] as const,
};
