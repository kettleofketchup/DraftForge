import api from '~/components/api/axios';
import {
  ConnectionCreateSchema,
  ConnectionPatchSchema,
  ConnectionSchema,
  ConnectionsSchema,
  DeliveryPageSchema,
  IssueKeyResponseSchema,
  RunPageSchema,
  RunSchema,
  type ApiConnection,
  type ConnectionCreate,
  type ConnectionPatch,
  type ConnectionRun,
  type DeliveryPage,
  type DeliveryState,
  type IssueKeyOptions,
  type IssuedKey,
  type RunPage,
} from './connectionSchemas';

const base = (orgId: number): string =>
  `/organizations/${orgId}/api-connections`;
const one = (orgId: number, connectionId: number): string =>
  `${base(orgId)}/${connectionId}`;

export async function listConnections(
  orgId: number,
  signal?: AbortSignal,
): Promise<ApiConnection[]> {
  const response = await api.get(`${base(orgId)}/`, { signal });
  return ConnectionsSchema.parse(response.data);
}

export async function getConnection(
  orgId: number,
  connectionId: number,
  signal?: AbortSignal,
): Promise<ApiConnection> {
  const response = await api.get(`${one(orgId, connectionId)}/`, { signal });
  return ConnectionSchema.parse(response.data);
}

export async function createConnection(
  orgId: number,
  body: ConnectionCreate,
): Promise<ApiConnection> {
  const response = await api.post(
    `${base(orgId)}/`,
    ConnectionCreateSchema.parse(body),
  );
  return ConnectionSchema.parse(response.data);
}

export async function updateConnection(
  orgId: number,
  connectionId: number,
  patch: ConnectionPatch,
): Promise<ApiConnection> {
  const response = await api.patch(
    `${one(orgId, connectionId)}/`,
    ConnectionPatchSchema.parse(patch),
  );
  return ConnectionSchema.parse(response.data);
}

export async function archiveConnection(
  orgId: number,
  connectionId: number,
): Promise<ApiConnection> {
  const response = await api.delete(`${one(orgId, connectionId)}/`);
  return ConnectionSchema.parse(response.data);
}

/**
 * Issues or rotates the inbound key. The raw key goes only to `onSecret`;
 * the resolved value is the redacted connection, safe for any cache.
 */
export async function issueConnectionKey(
  orgId: number,
  connectionId: number,
  options: IssueKeyOptions,
  onSecret: (key: IssuedKey) => void,
): Promise<ApiConnection> {
  const action = options.rotate ? 'rotate-key' : 'issue-key';
  const body = options.confirmed_operations
    ? { confirmed_operations: options.confirmed_operations }
    : {};
  const response = await api.post(
    `${one(orgId, connectionId)}/${action}/`,
    body,
  );
  const { connection, credential } = IssueKeyResponseSchema.parse(
    response.data,
  );
  onSecret(credential);
  return connection;
}

export async function revokeConnectionKey(
  orgId: number,
  connectionId: number,
): Promise<ApiConnection> {
  const response = await api.post(
    `${one(orgId, connectionId)}/revoke-key/`,
    {},
  );
  return ConnectionSchema.parse(response.data);
}

export async function listConnectionRuns(
  orgId: number,
  connectionId: number,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<RunPage> {
  const response = await api.get(`${one(orgId, connectionId)}/runs/`, {
    params: cursor ? { cursor } : {},
    signal,
  });
  return RunPageSchema.parse(response.data);
}

export async function getConnectionRun(
  orgId: number,
  connectionId: number,
  runId: string,
  signal?: AbortSignal,
): Promise<ConnectionRun> {
  const response = await api.get(`${one(orgId, connectionId)}/runs/${runId}/`, {
    signal,
  });
  return RunSchema.parse(response.data);
}

export async function listConnectionDeliveries(
  orgId: number,
  connectionId: number,
  filters: { state?: DeliveryState; cursor?: string | null } = {},
  signal?: AbortSignal,
): Promise<DeliveryPage> {
  const params: Record<string, string> = {};
  if (filters.state) params.state = filters.state;
  if (filters.cursor) params.cursor = filters.cursor;
  const response = await api.get(`${one(orgId, connectionId)}/deliveries/`, {
    params,
    signal,
  });
  return DeliveryPageSchema.parse(response.data);
}
