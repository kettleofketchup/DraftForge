import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { apiTokenKeys, type OrgFeatureAccess } from '~/features/org-features';
import {
  archiveConnection,
  createConnection,
  getConnection,
  getConnectionRun,
  issueConnectionKey,
  listConnectionRuns,
  listConnections,
  revokeConnectionKey,
  updateConnection,
} from './connectionApi';
import { connectionKeys } from './connectionQueryKeys';
import type {
  ApiConnection,
  ConnectionCreate,
  ConnectionPatch,
  ConnectionRun,
  IssueKeyOptions,
  IssuedKey,
  RunPage,
} from './connectionSchemas';

export function canManageConnections(access: OrgFeatureAccess): boolean {
  return access.settled && access.canUseApiTokens;
}

export function useConnections(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<ApiConnection[]> {
  return useQuery({
    queryKey: connectionKeys.list(orgId, access.viewerPk),
    queryFn: ({ signal }) => listConnections(orgId, signal),
    enabled: enabled && canManageConnections(access),
  });
}

export function useConnection(
  orgId: number,
  access: OrgFeatureAccess,
  connectionId: number | null,
  enabled = true,
): UseQueryResult<ApiConnection> {
  return useQuery({
    queryKey: connectionKeys.detail(orgId, access.viewerPk, connectionId ?? 0),
    queryFn: ({ signal }) => getConnection(orgId, connectionId ?? 0, signal),
    enabled: enabled && connectionId != null && canManageConnections(access),
  });
}

export function useConnectionRuns(
  orgId: number,
  access: OrgFeatureAccess,
  connectionId: number,
  enabled = true,
): UseQueryResult<RunPage> {
  return useQuery({
    queryKey: connectionKeys.runs(orgId, access.viewerPk, connectionId),
    queryFn: ({ signal }) =>
      listConnectionRuns(orgId, connectionId, null, signal),
    enabled: enabled && canManageConnections(access),
  });
}

export function useConnectionRun(
  orgId: number,
  access: OrgFeatureAccess,
  connectionId: number,
  runId: string | null,
): UseQueryResult<ConnectionRun> {
  return useQuery({
    queryKey: connectionKeys.run(
      orgId,
      access.viewerPk,
      connectionId,
      runId ?? '',
    ),
    queryFn: ({ signal }) =>
      getConnectionRun(orgId, connectionId, runId ?? '', signal),
    enabled: runId != null && canManageConnections(access),
  });
}

function storeConnection(
  queryClient: QueryClient,
  orgId: number,
  viewerPk: number | null,
  row: ApiConnection,
): Promise<void> {
  queryClient.setQueryData(connectionKeys.detail(orgId, viewerPk, row.id), row);
  queryClient.setQueryData<ApiConnection[]>(
    connectionKeys.list(orgId, viewerPk),
    (rows) => rows?.map((r) => (r.id === row.id ? row : r)),
  );
  return queryClient.invalidateQueries({
    queryKey: connectionKeys.list(orgId, viewerPk),
  });
}

function refreshKeys(
  queryClient: QueryClient,
  orgId: number,
  viewerPk: number | null,
): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: apiTokenKeys.tokens(orgId, viewerPk),
  });
}

export function useCreateConnection(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiConnection, unknown, ConnectionCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => createConnection(orgId, body),
    onSuccess: (row) =>
      storeConnection(queryClient, orgId, access.viewerPk, row),
  });
}

export interface UpdateConnectionInput {
  connectionId: number;
  patch: ConnectionPatch;
}

export function useUpdateConnection(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiConnection, unknown, UpdateConnectionInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ connectionId, patch }) =>
      updateConnection(orgId, connectionId, patch),
    onSuccess: (row) =>
      Promise.all([
        storeConnection(queryClient, orgId, access.viewerPk, row),
        refreshKeys(queryClient, orgId, access.viewerPk),
      ]),
  });
}

export function useArchiveConnection(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiConnection, unknown, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (connectionId) => archiveConnection(orgId, connectionId),
    onSuccess: (row) =>
      Promise.all([
        storeConnection(queryClient, orgId, access.viewerPk, row),
        refreshKeys(queryClient, orgId, access.viewerPk),
      ]),
  });
}

export function useRevokeConnectionKey(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiConnection, unknown, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (connectionId) => revokeConnectionKey(orgId, connectionId),
    onSuccess: (row) =>
      Promise.all([
        storeConnection(queryClient, orgId, access.viewerPk, row),
        refreshKeys(queryClient, orgId, access.viewerPk),
      ]),
  });
}

export interface IssueConnectionKeyInput extends IssueKeyOptions {
  connectionId: number;
}

/**
 * Issues or rotates a key. The raw key reaches only `onSecret`; mutation data
 * and variables hold redacted metadata, so no cache ever sees it.
 */
export function useIssueConnectionKey(
  orgId: number,
  access: OrgFeatureAccess,
  onSecret: (key: IssuedKey) => void,
): UseMutationResult<ApiConnection, unknown, IssueConnectionKeyInput> {
  const queryClient = useQueryClient();
  const secretRef = useRef(onSecret);
  useEffect(() => {
    secretRef.current = onSecret;
  }, [onSecret]);
  return useMutation({
    mutationFn: ({ connectionId, ...options }) =>
      issueConnectionKey(orgId, connectionId, options, (key) =>
        secretRef.current(key),
      ),
    onSuccess: (row) =>
      Promise.all([
        storeConnection(queryClient, orgId, access.viewerPk, row),
        refreshKeys(queryClient, orgId, access.viewerPk),
      ]),
  });
}

/**
 * Cancels and drops connection queries of a scope the viewer has left: a
 * previous org or viewer, or the current one once access is gone.
 */
export function useConnectionQueryHygiene(
  orgId: number,
  access: OrgFeatureAccess,
): void {
  const queryClient = useQueryClient();
  const allowed = canManageConnections(access);
  const viewerPk = access.viewerPk;
  const previous = useRef({ orgId, viewerPk });
  useEffect(() => {
    const drop = (scopeOrg: number, scopeViewer: number | null): void => {
      const queryKey = connectionKeys.all(scopeOrg, scopeViewer);
      void queryClient.cancelQueries({ queryKey });
      queryClient.removeQueries({ queryKey });
    };
    const prior = previous.current;
    if (prior.orgId !== orgId || prior.viewerPk !== viewerPk) {
      drop(prior.orgId, prior.viewerPk);
    }
    if (!allowed) drop(orgId, viewerPk);
    previous.current = { orgId, viewerPk };
  }, [queryClient, orgId, viewerPk, allowed]);
}
