import { z } from 'zod';
import {
  OPERATION_LABELS,
  TOKEN_NAME_MAX_LENGTH,
  operationLabel,
  type TokenFeature,
} from './schemas';

// Hand-written from backend/org/api_connections/types.py (ConnectionConfig).
export const CONNECTION_OPERATION_VALUES = [
  'mmr:read',
  'mmr:write',
  'promotion:read',
  'promotion:write',
  'promotion:import',
] as const;
export type ConnectionOperation = (typeof CONNECTION_OPERATION_VALUES)[number];

export interface ConnectionOperationInfo {
  value: ConnectionOperation;
  label: string;
  description: string;
  route: string;
  feature: TokenFeature;
  /** Kept for keys that already hold it; not offered on new grants. */
  legacy?: boolean;
}

export const CONNECTION_OPERATIONS: readonly ConnectionOperationInfo[] = [
  {
    value: 'mmr:read',
    label: OPERATION_LABELS['mmr:read'],
    description: "Reads members' assigned MMRs.",
    route: 'GET /api/organizations/{org}/mmr-sync/',
    feature: 'mmr_sync',
  },
  {
    value: 'mmr:write',
    label: OPERATION_LABELS['mmr:write'],
    description: "Pushes members' MMRs into DraftForge.",
    route: 'POST /api/organizations/{org}/mmr-sync/',
    feature: 'mmr_sync',
  },
  {
    value: 'promotion:read',
    label: OPERATION_LABELS['promotion:read'],
    description: "Reads a bound event's contact receipt history.",
    route: 'GET /api/organizations/{org}/integration/v1/contact-receipts/',
    feature: 'promotion',
  },
  {
    value: 'promotion:write',
    label: OPERATION_LABELS['promotion:write'],
    description:
      'Imports external contact receipts and the promotion points they award. It does not change templates or send messages.',
    route: 'POST /api/organizations/{org}/integration/v1/contact-receipts/',
    feature: 'promotion',
  },
  {
    value: 'promotion:import',
    label: OPERATION_LABELS['promotion:import'],
    description:
      'The original receipt import grant. Existing keys keep it; new keys use the write grant.',
    route: 'POST /api/organizations/{org}/integration/v1/contact-receipts/',
    feature: 'promotion',
    legacy: true,
  },
];

export const OUTBOUND_AUTH_VALUES = [
  'none',
  'bearer',
  'api_key_header',
  'api_key_field',
] as const;
export type OutboundAuth = (typeof OUTBOUND_AUTH_VALUES)[number];

export const OUTBOUND_AUTH_LABELS: Record<OutboundAuth, string> = {
  none: 'No credential',
  bearer: 'Bearer token',
  api_key_header: 'API key header',
  api_key_field: 'API key query or body field',
};

const JsonObjectSchema = z.record(z.string(), z.json());

const CredentialFieldSchema = z.object({
  location: z.enum(['query', 'body']),
  key: z.string(),
});

const ResponseMappingSchema = z.object({
  list_path: z.string(),
  player_id_path: z.string(),
  player_id_type: z.enum(['steam_account_id', 'steam64', 'discord_id']),
  mmr_path: z.string(),
});

const PaginationSchema = z.object({
  kind: z.enum(['none', 'page', 'cursor']),
  start: z.number().int(),
  page_size: z.number().int(),
  has_more_path: z.string().nullable(),
  next_cursor_path: z.string().nullable(),
});

export const MmrPushConfigSchema = z.object({
  path: z.string(),
  query: JsonObjectSchema,
  body: JsonObjectSchema.nullable(),
  credential_field: CredentialFieldSchema.nullable(),
});
export type MmrPushConfig = z.infer<typeof MmrPushConfigSchema>;

export const MmrPullConfigSchema = z.object({
  path: z.string(),
  method: z.enum(['GET', 'POST']),
  query: JsonObjectSchema,
  body: JsonObjectSchema.nullable(),
  credential_field: CredentialFieldSchema.nullable(),
  request_mode: z.enum(['org', 'member_batches', 'per_member']),
  acknowledge_per_member: z.boolean(),
  mapping: ResponseMappingSchema,
  pagination: PaginationSchema,
});
export type MmrPullConfig = z.infer<typeof MmrPullConfigSchema>;

export const RUN_STATE_VALUES = [
  'queued',
  'running',
  'partial',
  'succeeded',
  'failed',
  'canceled',
] as const;
export const RunStateSchema = z.enum(RUN_STATE_VALUES);
export type RunState = z.infer<typeof RunStateSchema>;

export const RunKindSchema = z.enum([
  'test',
  'mmr_pull',
  'mmr_push',
  'promotion_push',
]);

const COUNTER_FIELDS = {
  request_count: z.number().int(),
  row_count: z.number().int(),
  updated_count: z.number().int(),
  unchanged_count: z.number().int(),
  unmatched_count: z.number().int(),
  invalid_count: z.number().int(),
  conflict_count: z.number().int(),
  skipped_policy_count: z.number().int(),
  missing_identifier_count: z.number().int(),
  verified_count: z.number().int(),
  issue_count: z.number().int(),
};

// backend/org/api_connections/runs.py (run_summary); `{}` before any run.
export const RunSummarySchema = z.object({
  run_id: z.string(),
  kind: RunKindSchema,
  state: RunStateSchema,
  error_code: z.string(),
  ...COUNTER_FIELDS,
});
export type RunSummary = z.infer<typeof RunSummarySchema>;

const emptyToNull = (value: unknown): unknown =>
  value !== null &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  Object.keys(value).length === 0
    ? null
    : value;

// backend/org/api_connections/serializers.py (get_inbound_credentials).
export const ConnectionCredentialSchema = z.object({
  id: z.number(),
  prefix: z.string(),
  user_id: z.number().nullable(),
  issued_by_id: z.number().nullable(),
  operations: z.array(z.string()),
  created_at: z.string(),
  revoked_at: z.string().nullable(),
});
export type ConnectionCredential = z.infer<typeof ConnectionCredentialSchema>;

// backend/org/api_connections/serializers.py (ConnectionSerializer).
export const ConnectionSchema = z.object({
  id: z.number(),
  config_version: z.number().int(),
  name: z.string(),
  enabled: z.boolean(),
  inbound_enabled: z.boolean(),
  mmr_push_enabled: z.boolean(),
  mmr_pull_enabled: z.boolean(),
  promotion_push_enabled: z.boolean(),
  // Strings, not the enum, so a grant added on the backend still lists.
  operations: z.array(z.string()),
  outbound_base_url: z.string(),
  outbound_auth: z.enum(OUTBOUND_AUTH_VALUES),
  mmr_push_config: MmrPushConfigSchema,
  mmr_pull_config: MmrPullConfigSchema,
  game_type: z.number().int().nullable(),
  overwrite_policy: z.enum(['missing_only', 'unverified_only', 'replace']),
  mark_verified: z.boolean(),
  interval_minutes: z.number().int().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  archived_at: z.string().nullable(),
  created_by: z.number().nullable(),
  updated_by: z.number().nullable(),
  credential_present: z.boolean(),
  outbound_credential_owner: z.number().nullable(),
  outbound_authorizer: z.number().nullable(),
  outbound_credential_set_at: z.string().nullable(),
  inbound_credentials: z.array(ConnectionCredentialSchema),
  legacy_multi_credential: z.boolean(),
  last_run_summary: z.preprocess(emptyToNull, RunSummarySchema.nullable()),
  last_success_at: z.string().nullable(),
  last_error_code: z.string(),
  next_due_at: z.string().nullable(),
  promotion_stream: z.boolean(),
});
export type ApiConnection = z.infer<typeof ConnectionSchema>;

export const ConnectionsSchema = z.array(ConnectionSchema);

const CONFIG_PATCH_FIELDS = {
  name: z.string(),
  enabled: z.boolean(),
  inbound_enabled: z.boolean(),
  mmr_push_enabled: z.boolean(),
  mmr_pull_enabled: z.boolean(),
  promotion_push_enabled: z.boolean(),
  operations: z.array(z.enum(CONNECTION_OPERATION_VALUES)),
  outbound_base_url: z.string(),
  outbound_auth: z.enum(OUTBOUND_AUTH_VALUES),
  mmr_push_config: MmrPushConfigSchema,
  mmr_pull_config: MmrPullConfigSchema,
  game_type: z.number().int().nullable(),
  overwrite_policy: z.enum(['missing_only', 'unverified_only', 'replace']),
  mark_verified: z.boolean(),
  interval_minutes: z.number().int().nullable(),
  outbound_credential: z.string().min(1),
  clear_outbound_credential: z.literal(true),
};

const noDoubleCredential = (body: {
  outbound_credential?: string;
  clear_outbound_credential?: true;
}): boolean =>
  !(
    body.outbound_credential !== undefined &&
    body.clear_outbound_credential !== undefined
  );

/** POST api-connections/ body: any configuration subset, write-only credential included. */
export const ConnectionCreateSchema = z
  .object(CONFIG_PATCH_FIELDS)
  .partial()
  .strict()
  .refine(noDoubleCredential);
export type ConnectionCreate = z.infer<typeof ConnectionCreateSchema>;

/** PATCH api-connections/{id}/ body: changed fields plus the version they were edited from. */
export const ConnectionPatchSchema = z
  .object(CONFIG_PATCH_FIELDS)
  .partial()
  .extend({ config_version: z.number().int().min(1) })
  .strict()
  .refine(noDoubleCredential);
export type ConnectionPatch = z.infer<typeof ConnectionPatchSchema>;

export const IssuedKeySchema = z.object({
  id: z.number(),
  prefix: z.string(),
  token: z.string().min(1),
});
export type IssuedKey = z.infer<typeof IssuedKeySchema>;

// backend/org/api_connections/views.py (connection_key).
export const IssueKeyResponseSchema = z.object({
  connection: ConnectionSchema,
  credential: IssuedKeySchema,
});

export interface IssueKeyOptions {
  rotate: boolean;
  confirmed_operations?: string[];
}

const RunIssueSchema = z
  .object({ code: z.string() })
  .catchall(z.union([z.string(), z.number(), z.null()]));

// backend/org/api_connections/orchestration.py (run_row).
export const RunSchema = z.object({
  id: z.string(),
  kind: RunKindSchema,
  state: RunStateSchema,
  config_version: z.number().int(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error_code: z.string(),
  response_bytes: z.number().int(),
  ...COUNTER_FIELDS,
  requester: z.number().nullable(),
  trigger: z.string().nullable(),
  direction: z.string().nullable(),
  health_only: z.boolean(),
  worker_status: z
    .enum(['waiting_for_capacity', 'worker_unavailable'])
    .nullable(),
  issues: z.array(RunIssueSchema).optional(),
});
export type ConnectionRun = z.infer<typeof RunSchema>;

export const RunPageSchema = z.object({
  items: z.array(RunSchema),
  next_cursor: z.string().nullable(),
});
export type RunPage = z.infer<typeof RunPageSchema>;

export const DELIVERY_STATE_VALUES = ['pending', 'retry', 'paused'] as const;
export type DeliveryState = (typeof DELIVERY_STATE_VALUES)[number];

// backend/org/api_connections/views.py (_delivery_row, connection_deliveries).
export const DeliverySchema = z.object({
  delivery_id: z.string(),
  org_user_id: z.number().nullable(),
  game_type: z.number().int(),
  revision: z.number().int(),
  state: z.enum([
    'pending',
    'in_flight',
    'retry',
    'paused',
    'applied',
    'superseded',
    'canceled',
  ]),
  attempts: z.number().int(),
  due_at: z.string(),
  last_reason: z.string(),
  mmr: z.number().nullable(),
  steam_id: z.union([z.number(), z.string()]).nullable(),
  discord_id: z.string().nullable(),
  destination_origin: z.string(),
  created_at: z.string(),
});
export type ConnectionDelivery = z.infer<typeof DeliverySchema>;

export const DeliveryPageSchema = z.object({
  counts: z.object({
    pending: z.number().int(),
    retry: z.number().int(),
    paused: z.number().int(),
    in_flight: z.number().int(),
  }),
  items: z.array(DeliverySchema),
  next_cursor: z.string().nullable(),
});
export type DeliveryPage = z.infer<typeof DeliveryPageSchema>;

/** Fixed backend codes, as people read them. */
export const CONNECTION_ERROR_MESSAGES: Record<string, string> = {
  configuration_changed:
    'Someone else saved this connection. Reload it before saving again.',
  connection_archived: 'This connection is archived and cannot be changed.',
  invalid_config: 'The connection settings are not valid.',
  invalid_url:
    'Use an https:// address on the standard port, with no user name or password.',
  config_too_large: 'The connection settings are too large.',
  secret_like_literal:
    'A setting looks like a secret. Put credentials in the credential field.',
  credential_required:
    'An outbound credential is required for the selected authentication.',
  credential_required_for_new_origin:
    'The destination changed. Enter a new credential or clear the stored one.',
  credential_invalid: 'The credential could not be stored.',
  credential_keys_unavailable:
    'Credential storage is not configured on this server. Ask a site admin.',
  credential_key_unavailable:
    'Credential storage is not configured on this server. Ask a site admin.',
  not_promotion_stream:
    "Only the organization's promotion connection can push promotion contacts.",
  unsupported_auth: 'Promotion push needs bearer authentication.',
  promotion_stream_exists:
    'Another connection already holds the promotion grants for this organization.',
  promotion_stream_in_use:
    'This connection carries the promotion stream and cannot be archived.',
  binding_locked:
    'The destination cannot change after contacts have been imported.',
  inbound_disabled: 'Turn on inbound access and save before issuing a key.',
  operations_required: 'Grant at least one operation and save first.',
  credential_exists: 'This connection already has a key. Rotate it instead.',
  grant_confirmation_required:
    'Confirm the grants the new key will hold before issuing it.',
  authority_lost: 'Your account can no longer manage this connection.',
  rate_limited: 'Too many changes in a short time. Wait a minute and retry.',
};

export function connectionErrorCode(err: unknown): string | undefined {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data || typeof data !== 'object') return undefined;
  const code = (data as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

export function connectionErrorMessage(code: string): string {
  return CONNECTION_ERROR_MESSAGES[code] ?? `Request refused (${code}).`;
}

export const CREDENTIAL_ACTIONS = ['keep', 'replace', 'clear'] as const;

export const CONNECTION_NAME_MAX_LENGTH = TOKEN_NAME_MAX_LENGTH;

const ConnectionFormBase = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Name is required')
    .max(
      CONNECTION_NAME_MAX_LENGTH,
      `At most ${CONNECTION_NAME_MAX_LENGTH} characters`,
    ),
  enabled: z.boolean(),
  inbound_enabled: z.boolean(),
  operations: z.array(z.enum(CONNECTION_OPERATION_VALUES)),
  outbound_base_url: z
    .string()
    .trim()
    .max(2048, 'At most 2048 characters')
    .refine((value) => value === '' || httpsOrigin(value) !== null, {
      message:
        'Use an https:// address on the standard port, with no user name or password.',
    }),
  outbound_auth: z.enum(OUTBOUND_AUTH_VALUES),
  credential_action: z.enum(CREDENTIAL_ACTIONS),
  outbound_credential: z.string(),
});
export type ConnectionForm = z.infer<typeof ConnectionFormBase>;

/** The canonical origin of an https URL on port 443, else null. */
export function httpsOrigin(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    if (url.port && url.port !== '443') return null;
    return url.origin;
  } catch {
    return null;
  }
}

function originChanged(saved: ApiConnection, url: string): boolean {
  return httpsOrigin(saved.outbound_base_url) !== httpsOrigin(url);
}

/** The draft schema; `saved` is the row the draft was edited from, null when creating. */
export function ConnectionFormSchema(saved: ApiConnection | null) {
  return ConnectionFormBase.superRefine((values, ctx) => {
    if (values.outbound_auth === 'none') return;
    if (
      values.credential_action === 'replace' &&
      values.outbound_credential.length === 0
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['outbound_credential'],
        message: 'Enter the credential, or cancel replacing it.',
      });
    }
    if (
      saved?.credential_present &&
      values.credential_action === 'keep' &&
      originChanged(saved, values.outbound_base_url)
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['outbound_credential'],
        message:
          'The destination changed. Enter a new credential or clear the stored one.',
      });
    }
  });
}

export function connectionFormDefaults(): ConnectionForm {
  return {
    name: '',
    enabled: false,
    inbound_enabled: false,
    operations: [],
    outbound_base_url: '',
    outbound_auth: 'none',
    credential_action: 'keep',
    outbound_credential: '',
  };
}

function knownOperations(values: readonly string[]): ConnectionOperation[] {
  return CONNECTION_OPERATION_VALUES.filter((op) => values.includes(op));
}

export function connectionFormValues(saved: ApiConnection): ConnectionForm {
  return {
    name: saved.name,
    enabled: saved.enabled,
    inbound_enabled: saved.inbound_enabled,
    operations: knownOperations(saved.operations),
    outbound_base_url: saved.outbound_base_url,
    outbound_auth: saved.outbound_auth,
    credential_action: 'keep',
    outbound_credential: '',
  };
}

function sameOperations(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((op) => b.includes(op));
}

function changedFields(
  from: ConnectionForm,
  values: ConnectionForm,
): Omit<ConnectionPatch, 'config_version'> {
  const body: Omit<ConnectionPatch, 'config_version'> = {};
  const name = values.name.trim();
  if (name !== from.name) body.name = name;
  if (values.enabled !== from.enabled) body.enabled = values.enabled;
  if (values.inbound_enabled !== from.inbound_enabled) {
    body.inbound_enabled = values.inbound_enabled;
  }
  if (!sameOperations(values.operations, from.operations)) {
    body.operations = knownOperations(values.operations);
  }
  const url = values.outbound_base_url.trim();
  if (url !== from.outbound_base_url) body.outbound_base_url = url;
  if (values.outbound_auth !== from.outbound_auth) {
    body.outbound_auth = values.outbound_auth;
  }
  if (values.outbound_auth !== 'none') {
    if (values.credential_action === 'replace' && values.outbound_credential) {
      body.outbound_credential = values.outbound_credential;
    } else if (values.credential_action === 'clear') {
      body.clear_outbound_credential = true;
    }
  }
  return body;
}

export function buildConnectionPatch(
  saved: ApiConnection,
  values: ConnectionForm,
): ConnectionPatch {
  return {
    config_version: saved.config_version,
    ...changedFields(connectionFormValues(saved), values),
  };
}

export function buildConnectionCreate(
  values: ConnectionForm,
): ConnectionCreate {
  return {
    name: values.name.trim(),
    ...changedFields(connectionFormDefaults(), values),
  };
}

/** Which draft field a backend error code belongs to, if any. */
export function connectionErrorField(
  code: string,
): keyof ConnectionForm | null {
  switch (code) {
    case 'credential_required':
    case 'credential_required_for_new_origin':
    case 'credential_invalid':
      return 'outbound_credential';
    case 'invalid_url':
    case 'binding_locked':
      return 'outbound_base_url';
    case 'promotion_stream_exists':
      return 'operations';
    default:
      return null;
  }
}

export function operationLabelList(operations: readonly string[]): string {
  return operations.map(operationLabel).join(', ');
}
