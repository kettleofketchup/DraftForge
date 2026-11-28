import { z } from 'zod';
import {
  DEFAULT_PULL_CONFIG,
  DEFAULT_PUSH_CONFIG,
  INTERVAL_MAX,
  INTERVAL_MIN,
  PullFormSchema,
  PushFormSchema,
  pullConfigFromForm,
  pullFormValues,
  pullIssues,
  pushConfigFromForm,
  pushFormValues,
  pushIssues,
} from './connectionSyncSchemas';
import {
  ApiUserRefSchema,
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
  /** The authorizer for auth none, else the credential owner. */
  outbound_principal: ApiUserRefSchema.nullable(),
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
  reasons: z.object({ paused: z.record(z.string(), z.number().int()) }),
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
  per_member_acknowledgement_required:
    'Per-member mode needs more than 100 requests. Confirm the request count on the MMR pull tab and save.',
  credential_unavailable:
    'The stored credential could not be used. Replace it on the General tab.',
  credential_binding_invalid:
    'The stored credential belongs to another destination. Replace it on the General tab.',
  confirmation_required: 'Confirm this action before it runs.',
  backlog_changed:
    'The number of held sends changed. Review the new count and confirm again.',
  managed_by_deployment:
    'Promotion sync for this organization is set in the server configuration. A site operator must move it here first.',
  guild_missing: 'Link a Discord server to this organization first.',
  foreign_event: 'One of the events does not belong to this organization.',
  invalid_binding: 'Each event needs one distinct event ID and occasion ID.',
  not_found: 'That item no longer exists.',
  invalid_request: 'The request was not valid.',
  not_permitted: 'Your account cannot do this.',
  worker_unavailable:
    'No sync worker has picked this run up. Ask a site admin to check the workers.',
  waiting_for_capacity:
    "Waiting for the organization's other outbound requests to finish.",
  dns_failed: 'The destination host name could not be resolved.',
  unsafe_address:
    'The destination resolves to a private or reserved address and is blocked.',
  peer_mismatch: 'The destination answered from an unexpected address.',
  redirect_forbidden:
    'The destination answered with a redirect. Use its final address.',
  deadline_exceeded: 'The destination did not answer within 15 seconds.',
  network_failed: 'The destination could not be reached.',
  response_too_large: 'The response was larger than the 1 MiB page limit.',
  request_too_large: 'The request was larger than allowed.',
  invalid_json: 'The response was not valid JSON.',
  invalid_compression: 'The response could not be decompressed.',
  unsupported_encoding: 'The response used an unsupported encoding.',
  unsupported_media_type: 'The response was not JSON.',
  invalid_origin: 'The destination address is not valid.',
  pagination_loop: 'The destination returned the same page twice.',
  pull_incomplete:
    'The destination had more rows than one run may fetch. Nothing was imported.',
  pull_ambiguous: 'The response could not be matched unambiguously.',
  member_limit_exceeded:
    'The organization has more members than one run may cover.',
  cursor_too_large: 'The next cursor was larger than 1 KiB.',
  missing_identifier: 'A member had no identifier for this request.',
  run_deadline_exceeded: 'The run took longer than 10 minutes and stopped.',
  run_abandoned: 'The run stopped responding and was ended.',
  auth_failed:
    'The destination rejected the credential. Replace it, then resume.',
  schema_rejected:
    'The destination rejected the request. Fix the push settings, then resume.',
  origin_changed:
    'The destination changed after these were queued. Resync to send current values to the new destination.',
  invalid_acknowledgement:
    'The destination sent an answer DraftForge does not understand.',
  sync_loop_suspected: 'Paused because the same change kept coming back.',
  unmatched: 'No member matched this player ID.',
  ambiguous_duplicate:
    'Several rows named the same member with different values; none applied.',
  invalid_entry: 'This row is not an object.',
  invalid_envelope: 'The player list was not found at the configured path.',
  invalid_identifier: 'The player ID is missing or not a valid ID.',
  invalid_mmr: 'The MMR is not a whole number in range.',
  missing_mmr: 'The row has no MMR field.',
  conflict: 'The MMR changed in DraftForge during the run; it was kept.',
  skipped_policy: 'Kept by the overwrite rule.',
  invalid_credential:
    'The stored credential cannot be sent to this destination. Replace it on the General tab.',
  shared_credential:
    "This credential is the server's shared promotion key. Use a credential issued for this organization.",
  destination_conflict:
    'The promotion connection already points at a different destination.',
  promotion_keys_elsewhere:
    'Another connection holds an active key with promotion grants. Revoke it first.',
  operator_required: 'Only a site operator can do this.',
  not_legacy_bound:
    'This organization has no promotion sync in the server configuration.',
  unsafe_destination:
    'The destination address is not allowed. Use a public https:// address.',
  binding_mismatch:
    "The configured Discord server does not match this organization's server.",
  invalid_cursor: 'The list changed. Reload it and try again.',
  membership_removed: 'The member left the organization.',
  superseded: 'A newer MMR for this member replaced this one.',
  resynced: 'Canceled by a resync, which queued the current MMR instead.',
  unsupported_kind: 'This kind of run is not supported.',
  timeout: 'The destination did not answer in time.',
  connection_error: 'The destination could not be reached.',
  transport_error: 'The request to the destination failed.',
  server_error: 'The destination had a server error.',
  invalid_response:
    'The destination sent a response DraftForge could not read.',
  adaptor_unauthorized:
    'The destination rejected the credential. Replace it, then resume.',
  adaptor_forbidden:
    'The destination refused access for this credential. Check its permissions, then resume.',
  adaptor_rejected: 'The destination rejected the send.',
  adaptor_unavailable: 'The destination is temporarily unavailable.',
  mapping_required:
    'The destination does not recognize this event. Map it there first.',
  idempotency_conflict:
    'The destination already holds a different send with the same ID.',
  direction_disabled: 'Promotion push is turned off for this connection.',
  writeback_disabled: 'The destination has recording turned off.',
  dry_run: 'The destination is in test mode and recorded nothing.',
  payload_integrity: 'The stored send failed its integrity check.',
  retries_exhausted: 'The send failed too many times and stopped retrying.',
  dispatch_error: 'An internal error stopped the send.',
  account_deleted: 'The member deleted their account.',
};

export function connectionErrorCode(err: unknown): string | undefined {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data || typeof data !== 'object') return undefined;
  const code = (data as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

export function connectionErrorMessage(code: string): string {
  const known = CONNECTION_ERROR_MESSAGES[code];
  if (known) return known;
  const http = /^http_(\d{3})$/.exec(code);
  if (http) return `The destination answered HTTP ${http[1]}.`;
  return `Request refused (${code}).`;
}

export const CREDENTIAL_ACTIONS = ['keep', 'replace', 'clear'] as const;

export const OVERWRITE_POLICY_VALUES = [
  'missing_only',
  'unverified_only',
  'replace',
] as const;
export type OverwritePolicy = (typeof OVERWRITE_POLICY_VALUES)[number];

export const OVERWRITE_POLICY_LABELS: Record<OverwritePolicy, string> = {
  missing_only: 'Only fill missing MMRs',
  unverified_only: 'Replace unverified MMRs',
  replace: 'Replace any MMR',
};

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
  mmr_push_enabled: z.boolean(),
  mmr_pull_enabled: z.boolean(),
  promotion_push_enabled: z.boolean(),
  game_type: z.number().int().nullable(),
  overwrite_policy: z.enum(OVERWRITE_POLICY_VALUES),
  mark_verified: z.boolean(),
  interval_minutes: z
    .number({ error: 'Enter a number of minutes' })
    .int('Use whole minutes')
    .min(INTERVAL_MIN, `At least ${INTERVAL_MIN} minutes`)
    .max(INTERVAL_MAX, `At most ${INTERVAL_MAX} minutes (one week)`)
    .nullable(),
  push: PushFormSchema,
  pull: PullFormSchema,
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

export interface ConnectionFormOptions {
  /** The org's saved member count, for the per-member request estimate. */
  memberCount?: number | null;
}

/** The draft schema; `saved` is the row the draft was edited from, null when creating. */
export function ConnectionFormSchema(
  saved: ApiConnection | null,
  options: ConnectionFormOptions = {},
) {
  return ConnectionFormBase.superRefine((values, ctx) => {
    const sync = {
      auth: values.outbound_auth,
      pushEnabled: values.mmr_push_enabled,
      pullEnabled: values.mmr_pull_enabled,
      memberCount: options.memberCount,
    };
    for (const issue of [
      ...pushIssues(values.push, sync),
      ...pullIssues(values.pull, sync),
    ]) {
      ctx.addIssue({
        code: 'custom',
        path: issue.path,
        message: issue.message,
      });
    }
    const outbound =
      values.mmr_push_enabled ||
      values.mmr_pull_enabled ||
      values.promotion_push_enabled;
    if (outbound && !values.outbound_base_url.trim()) {
      ctx.addIssue({
        code: 'custom',
        path: ['outbound_base_url'],
        message:
          'Enter the destination before turning on an outbound direction.',
      });
    }
    if (values.promotion_push_enabled && values.outbound_auth !== 'bearer') {
      ctx.addIssue({
        code: 'custom',
        path: ['promotion_push_enabled'],
        message: 'Promotion push needs bearer authentication.',
      });
    }
    if (values.outbound_auth === 'none') return;
    if (
      outbound &&
      values.credential_action !== 'replace' &&
      (!saved?.credential_present || values.credential_action === 'clear')
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['outbound_credential'],
        message: 'Add the credential before turning on an outbound direction.',
      });
    }
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
    mmr_push_enabled: false,
    mmr_pull_enabled: false,
    promotion_push_enabled: false,
    game_type: null,
    overwrite_policy: 'missing_only',
    mark_verified: false,
    interval_minutes: null,
    push: pushFormValues(DEFAULT_PUSH_CONFIG),
    pull: pullFormValues(DEFAULT_PULL_CONFIG),
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
    mmr_push_enabled: saved.mmr_push_enabled,
    mmr_pull_enabled: saved.mmr_pull_enabled,
    promotion_push_enabled: saved.promotion_push_enabled,
    game_type: saved.game_type,
    overwrite_policy: saved.overwrite_policy,
    mark_verified: saved.mark_verified,
    interval_minutes: saved.interval_minutes,
    push: pushFormValues(saved.mmr_push_config),
    pull: pullFormValues(saved.mmr_pull_config),
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
  for (const flag of [
    'mmr_push_enabled',
    'mmr_pull_enabled',
    'promotion_push_enabled',
    'mark_verified',
  ] as const) {
    if (values[flag] !== from[flag]) body[flag] = values[flag];
  }
  if (values.game_type !== from.game_type) body.game_type = values.game_type;
  if (values.overwrite_policy !== from.overwrite_policy) {
    body.overwrite_policy = values.overwrite_policy;
  }
  if (values.interval_minutes !== from.interval_minutes) {
    body.interval_minutes = values.interval_minutes;
  }
  // Auth decides where the key slot goes, so compare rendered configs.
  const push = pushConfigFromForm(values.push, values.outbound_auth);
  if (
    JSON.stringify(push) !==
    JSON.stringify(pushConfigFromForm(from.push, from.outbound_auth))
  ) {
    body.mmr_push_config = push;
  }
  const pull = pullConfigFromForm(values.pull, values.outbound_auth);
  if (
    JSON.stringify(pull) !==
    JSON.stringify(pullConfigFromForm(from.pull, from.outbound_auth))
  ) {
    body.mmr_pull_config = pull;
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
    case 'not_promotion_stream':
    case 'unsupported_auth':
      return 'promotion_push_enabled';
    default:
      return null;
  }
}

export function operationLabelList(operations: readonly string[]): string {
  return operations.map(operationLabel).join(', ');
}

export const TEST_DIRECTIONS = [
  'mmr_pull',
  'mmr_push',
  'promotion_push',
] as const;
export type TestDirection = (typeof TEST_DIRECTIONS)[number];

// backend/org/api_connections/views.py (connection_test).
export const TestStartedSchema = z.object({
  run_id: z.string(),
  state: RunStateSchema,
});

export const ResumedSchema = z.object({ resumed: z.number().int() });
export const EnqueuedSchema = z.object({ enqueued: z.number().int() });
export const ReleasedSchema = z.object({ released: z.number().int() });

// backend/org/api_connections/promotion_config.py (describe).
export const PromotionStreamSchema = z.object({
  source: z.enum(['deployment', 'connection', 'none']),
  adopted: z.boolean(),
  connection_id: z.number().nullable(),
  guild_id: z.string().nullable(),
  events: z.array(
    z.object({
      event_id: z.string(),
      occasion_id: z.string(),
      effective_at: z.string().nullable(),
    }),
  ),
  transport: z.enum(['env', 'connection', 'held', 'none']),
});
export type PromotionStream = z.infer<typeof PromotionStreamSchema>;

export const PROMOTION_OUTBOX_STATES = [
  'pending',
  'in_flight',
  'retry',
  'paused',
  'backlog_held',
  'reconciliation_required',
  'applied',
  'canceled',
] as const;
export type PromotionOutboxState = (typeof PROMOTION_OUTBOX_STATES)[number];

// backend/org/api_connections/recovery.py (promotion_outbox_summary).
export const PromotionOutboxSchema = z.object({
  counts: z.record(z.enum(PROMOTION_OUTBOX_STATES), z.number().int()),
  reasons: z.object({
    retry: z.record(z.string(), z.number().int()),
    paused: z.record(z.string(), z.number().int()),
    reconciliation_required: z.record(z.string(), z.number().int()),
  }),
});
export type PromotionOutbox = z.infer<typeof PromotionOutboxSchema>;

export interface PromotionEventBinding {
  event_id: string;
  occasion_id: string;
}
