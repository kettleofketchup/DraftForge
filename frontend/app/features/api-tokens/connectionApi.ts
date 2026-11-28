import api from '~/components/api/axios';
import {
  ConnectionCreateSchema,
  ConnectionPatchSchema,
  ConnectionSchema,
  ConnectionsSchema,
  DeliveryPageSchema,
  EnqueuedSchema,
  IssueKeyResponseSchema,
  PromotionOutboxSchema,
  PromotionStreamSchema,
  ReleasedSchema,
  ResumedSchema,
  RunPageSchema,
  RunSchema,
  TestStartedSchema,
  type ApiConnection,
  type ConnectionCreate,
  type ConnectionPatch,
  type ConnectionRun,
  type DeliveryPage,
  type DeliveryState,
  type IssueKeyOptions,
  type IssuedKey,
  type PromotionEventBinding,
  type PromotionOutbox,
  type PromotionStream,
  type RunPage,
  type TestDirection,
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
  // The server has already minted the key: hand it over before any other check.
  const { credential } = IssueKeyResponseSchema.pick({
    credential: true,
  }).parse(response.data);
  onSecret(credential);
  return IssueKeyResponseSchema.parse(response.data).connection;
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

/** Queues a test of the saved configuration; it never enables sync. */
export async function testConnection(
  orgId: number,
  connectionId: number,
  direction: TestDirection,
): Promise<string> {
  const response = await api.post(`${one(orgId, connectionId)}/test/`, {
    direction,
  });
  return TestStartedSchema.parse(response.data).run_id;
}

/** Queues a pull with the saved configuration, or returns the active one. */
export async function pullConnection(
  orgId: number,
  connectionId: number,
): Promise<ConnectionRun> {
  const response = await api.post(`${one(orgId, connectionId)}/pull/`, {});
  return RunSchema.parse(response.data);
}

export async function resumeConnectionDeliveries(
  orgId: number,
  connectionId: number,
  configVersion: number,
): Promise<number> {
  const response = await api.post(
    `${one(orgId, connectionId)}/deliveries/resume/`,
    { config_version: configVersion },
  );
  return ResumedSchema.parse(response.data).resumed;
}

export async function resyncConnectionDeliveries(
  orgId: number,
  connectionId: number,
  configVersion: number,
): Promise<number> {
  const response = await api.post(
    `${one(orgId, connectionId)}/deliveries/resync/`,
    { config_version: configVersion, confirm: true },
  );
  return EnqueuedSchema.parse(response.data).enqueued;
}

export async function getPromotionStream(
  orgId: number,
  signal?: AbortSignal,
): Promise<PromotionStream> {
  const response = await api.get(`${base(orgId)}/promotion/`, { signal });
  return PromotionStreamSchema.parse(response.data);
}

export async function setPromotionBinding(
  orgId: number,
  connectionId: number,
  events: PromotionEventBinding[],
): Promise<PromotionStream> {
  const response = await api.put(
    `${one(orgId, connectionId)}/promotion-binding/`,
    { events },
  );
  return PromotionStreamSchema.parse(response.data);
}

export async function getPromotionOutbox(
  orgId: number,
  connectionId: number,
  signal?: AbortSignal,
): Promise<PromotionOutbox> {
  const response = await api.get(
    `${one(orgId, connectionId)}/promotion/outbox/`,
    { signal },
  );
  return PromotionOutboxSchema.parse(response.data);
}

export async function resumePromotionOutbox(
  orgId: number,
  connectionId: number,
): Promise<number> {
  const response = await api.post(
    `${one(orgId, connectionId)}/promotion/resume/`,
    {},
  );
  return ResumedSchema.parse(response.data).resumed;
}

export async function sendPromotionBacklog(
  orgId: number,
  connectionId: number,
  confirmedCount: number,
): Promise<number> {
  const response = await api.post(
    `${one(orgId, connectionId)}/promotion/send-backlog/`,
    { confirmed_count: confirmedCount },
  );
  return ReleasedSchema.parse(response.data).released;
}
