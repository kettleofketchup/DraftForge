import { z } from 'zod';

import type {
  MmrPullConfig,
  MmrPushConfig,
  OutboundAuth,
} from './connectionSchemas';

/** backend/org/api_connections/schemas.py PLACEHOLDERS, as people read them. */
export const PLACEHOLDERS = [
  { value: '{{org.id}}', field: 'org_id', label: 'Org ID', scope: 'any' },
  {
    value: '{{game_type}}',
    field: 'game_type',
    label: 'Game type',
    scope: 'any',
  },
  {
    value: '{{players.steam_account_ids}}',
    field: 'steam_account_ids',
    label: 'Member Steam account IDs',
    scope: 'batch',
  },
  {
    value: '{{players.steam64_ids}}',
    field: 'steam64_ids',
    label: 'Member Steam64 IDs',
    scope: 'batch',
  },
  {
    value: '{{players.discord_ids}}',
    field: 'discord_ids',
    label: 'Member Discord IDs',
    scope: 'batch',
  },
  {
    value: '{{player.steam_account_id}}',
    field: 'steam_account_id',
    label: "One member's Steam account ID",
    scope: 'member',
  },
  {
    value: '{{player.steam64}}',
    field: 'steam64',
    label: "One member's Steam64 ID",
    scope: 'member',
  },
  {
    value: '{{player.discord_id}}',
    field: 'discord_id',
    label: "One member's Discord ID",
    scope: 'member',
  },
  { value: '{{page}}', field: 'page', label: 'Page number', scope: 'page' },
  {
    value: '{{page_size}}',
    field: 'page_size',
    label: 'Page size',
    scope: 'paging',
  },
  { value: '{{cursor}}', field: 'cursor', label: 'Cursor', scope: 'cursor' },
] as const;
export type Placeholder = (typeof PLACEHOLDERS)[number]['value'];

const PLACEHOLDER_VALUES: readonly string[] = PLACEHOLDERS.map((p) => p.value);

/** backend push._render_query fills only these. */
export const PUSH_PLACEHOLDERS: readonly string[] = [
  '{{org.id}}',
  '{{game_type}}',
];

export function placeholderLabel(value: string): string {
  return PLACEHOLDERS.find((p) => p.value === value)?.label ?? value;
}

const CREDENTIAL_SLOT = '{{credential}}';

/** backend SENSITIVE_KEYS, compared with - and _ removed, case-insensitively. */
const SENSITIVE_KEYS = new Set([
  'apikey',
  'key',
  'token',
  'accesstoken',
  'secret',
  'password',
  'auth',
  'authorization',
  'signature',
  'sig',
]);

export function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.has(key.replace(/[-_]/g, '').toLowerCase());
}

export const TEMPLATE_KINDS = [
  'text',
  'number',
  'boolean',
  'variable',
  'json',
] as const;
export type TemplateKind = (typeof TEMPLATE_KINDS)[number];

export const TEMPLATE_KIND_LABELS: Record<TemplateKind, string> = {
  text: 'Text',
  number: 'Number',
  boolean: 'True/false',
  variable: 'Variable',
  json: 'Kept as saved',
};

export const TemplateRowSchema = z.object({
  key: z.string(),
  kind: z.enum(TEMPLATE_KINDS),
  value: z.string(),
});
export type TemplateRow = z.infer<typeof TemplateRowSchema>;

export const CREDENTIAL_LOCATIONS = ['none', 'query', 'body'] as const;

const RequestFormBase = {
  path: z.string(),
  query: z.array(TemplateRowSchema),
  credential_location: z.enum(CREDENTIAL_LOCATIONS),
  credential_key: z.string(),
};

export const PushFormSchema = z.object(RequestFormBase);
export type PushForm = z.infer<typeof PushFormSchema>;

export const PullFormSchema = z.object({
  ...RequestFormBase,
  method: z.enum(['GET', 'POST']),
  body: z.array(TemplateRowSchema),
  request_mode: z.enum(['org', 'member_batches', 'per_member']),
  acknowledge_per_member: z.boolean(),
  list_path: z.string(),
  player_id_path: z.string(),
  player_id_type: z.enum(['steam_account_id', 'steam64', 'discord_id']),
  mmr_path: z.string(),
  pagination_kind: z.enum(['none', 'page', 'cursor']),
  pagination_start: z.number(),
  page_size: z.number(),
  has_more_path: z.string(),
  next_cursor_path: z.string(),
});
export type PullForm = z.infer<typeof PullFormSchema>;

export const REQUEST_MODE_LABELS: Record<PullForm['request_mode'], string> = {
  org: 'Organization (one paged query)',
  member_batches: 'Member batches (100 members per request)',
  per_member: 'Per member (one request each)',
};

export const PLAYER_ID_TYPE_LABELS: Record<PullForm['player_id_type'], string> =
  {
    steam_account_id: 'Steam account ID',
    steam64: 'Steam64 ID',
    discord_id: 'Discord ID',
  };

export const PAGINATION_LABELS: Record<PullForm['pagination_kind'], string> = {
  none: 'None',
  page: 'Page number',
  cursor: 'Cursor',
};

function toRow(key: string, value: unknown): TemplateRow {
  if (typeof value === 'string') {
    return PLACEHOLDER_VALUES.includes(value)
      ? { key, kind: 'variable', value }
      : { key, kind: 'text', value };
  }
  if (typeof value === 'number')
    return { key, kind: 'number', value: `${value}` };
  if (typeof value === 'boolean') {
    return { key, kind: 'boolean', value: value ? 'true' : 'false' };
  }
  return { key, kind: 'json', value: JSON.stringify(value) };
}

function toRows(
  values: Record<string, unknown> | null,
  skip: string | null,
): TemplateRow[] {
  return Object.entries(values ?? {})
    .filter(([key]) => key !== skip)
    .map(([key, value]) => toRow(key, value));
}

function fromRow(row: TemplateRow): unknown {
  switch (row.kind) {
    case 'number':
      return Number(row.value);
    case 'boolean':
      return row.value === 'true';
    case 'json':
      return JSON.parse(row.value) as unknown;
    default:
      return row.value;
  }
}

type JsonValue = MmrPullConfig['query'][string];
type JsonMap = Record<string, JsonValue>;

function fromRows(rows: readonly TemplateRow[]): JsonMap {
  const out: JsonMap = {};
  for (const row of rows) {
    out[row.key.trim()] = fromRow(row) as JsonValue;
  }
  return out;
}

function credentialLocation(
  field: { location: 'query' | 'body'; key: string } | null,
): Pick<PushForm, 'credential_location' | 'credential_key'> {
  return field
    ? { credential_location: field.location, credential_key: field.key }
    : { credential_location: 'none', credential_key: '' };
}

export function pushFormValues(config: MmrPushConfig): PushForm {
  const field = config.credential_field;
  return {
    path: config.path,
    query: toRows(config.query, field?.location === 'query' ? field.key : null),
    ...credentialLocation(field),
  };
}

export function pullFormValues(config: MmrPullConfig): PullForm {
  const field = config.credential_field;
  return {
    path: config.path,
    method: config.method,
    query: toRows(config.query, field?.location === 'query' ? field.key : null),
    body: toRows(config.body, field?.location === 'body' ? field.key : null),
    ...credentialLocation(field),
    request_mode: config.request_mode,
    acknowledge_per_member: config.acknowledge_per_member,
    list_path: config.mapping.list_path,
    player_id_path: config.mapping.player_id_path,
    player_id_type: config.mapping.player_id_type,
    mmr_path: config.mapping.mmr_path,
    pagination_kind: config.pagination.kind,
    pagination_start: config.pagination.start,
    page_size: config.pagination.page_size,
    has_more_path: config.pagination.has_more_path ?? '',
    next_cursor_path: config.pagination.next_cursor_path ?? '',
  };
}

function credentialField(
  form: Pick<PushForm, 'credential_location' | 'credential_key'>,
  auth: OutboundAuth,
): { location: 'query' | 'body'; key: string } | null {
  if (auth !== 'api_key_field' || form.credential_location === 'none') {
    return null;
  }
  return {
    location: form.credential_location,
    key: form.credential_key.trim(),
  };
}

export function pushConfigFromForm(
  form: PushForm,
  auth: OutboundAuth,
): MmrPushConfig {
  const field = credentialField(form, auth);
  const query = fromRows(form.query);
  if (field?.location === 'query') query[field.key] = CREDENTIAL_SLOT;
  return {
    path: form.path.trim(),
    query,
    body: field?.location === 'body' ? { [field.key]: CREDENTIAL_SLOT } : null,
    credential_field: field,
  };
}

export function pullConfigFromForm(
  form: PullForm,
  auth: OutboundAuth,
): MmrPullConfig {
  const field = credentialField(form, auth);
  const query = fromRows(form.query);
  if (field?.location === 'query') query[field.key] = CREDENTIAL_SLOT;
  let body: JsonMap | null = null;
  if (form.method === 'POST') {
    body = fromRows(form.body);
    if (field?.location === 'body') body[field.key] = CREDENTIAL_SLOT;
    if (Object.keys(body).length === 0) body = null;
  }
  const optional = (value: string): string | null => value.trim() || null;
  return {
    path: form.path.trim(),
    method: form.method,
    query,
    body,
    credential_field: field,
    request_mode: form.request_mode,
    acknowledge_per_member: form.acknowledge_per_member,
    mapping: {
      list_path: form.list_path.trim(),
      player_id_path: form.player_id_path.trim(),
      player_id_type: form.player_id_type,
      mmr_path: form.mmr_path.trim(),
    },
    pagination: {
      kind: form.pagination_kind,
      start: form.pagination_start,
      page_size: form.page_size,
      has_more_path:
        form.pagination_kind === 'page' ? optional(form.has_more_path) : null,
      next_cursor_path:
        form.pagination_kind === 'cursor'
          ? optional(form.next_cursor_path)
          : null,
    },
  };
}

/** backend types.MmrPushConfig defaults. */
export const DEFAULT_PUSH_CONFIG: MmrPushConfig = {
  path: '/api/v1/organizations/{org_id}/mmr',
  query: {},
  body: null,
  credential_field: null,
};

/** backend types.MmrPullConfig defaults. */
export const DEFAULT_PULL_CONFIG: MmrPullConfig = {
  path: '/',
  method: 'GET',
  query: {},
  body: null,
  credential_field: null,
  request_mode: 'org',
  acknowledge_per_member: false,
  mapping: {
    list_path: '',
    player_id_path: 'id',
    player_id_type: 'steam_account_id',
    mmr_path: 'mmr',
  },
  pagination: {
    kind: 'none',
    start: 1,
    page_size: 500,
    has_more_path: null,
    next_cursor_path: null,
  },
};

/** The backend asks for a key slot once the pull config leaves its defaults. */
function isDefaultPull(form: PullForm): boolean {
  const normalize = (f: PullForm): string =>
    JSON.stringify(pullConfigFromForm(f, 'none'));
  return normalize(form) === normalize(pullFormValues(DEFAULT_PULL_CONFIG));
}

/** Run cap: backend limits.REQUESTS_PER_RUN. */
export const REQUESTS_PER_RUN = 100;
const MEMBER_BATCH = 100;

/** Requests one run needs, from the org's member count; null when unknown. */
export function estimateRequests(
  form: Pick<PullForm, 'request_mode' | 'pagination_kind' | 'page_size'>,
  memberCount: number | null | undefined,
): number | null {
  if (memberCount == null) return null;
  const members = Math.max(memberCount, 0);
  switch (form.request_mode) {
    case 'per_member':
      return members;
    case 'member_batches':
      return Math.max(1, Math.ceil(members / MEMBER_BATCH));
    default:
      return form.pagination_kind === 'none'
        ? 1
        : Math.max(1, Math.ceil(members / Math.max(form.page_size, 1)));
  }
}

export function needsPerMemberAck(
  form: Pick<PullForm, 'request_mode' | 'pagination_kind' | 'page_size'>,
  memberCount: number | null | undefined,
): boolean {
  if (form.request_mode !== 'per_member') return false;
  const estimate = estimateRequests(form, memberCount);
  return estimate === null || estimate > REQUESTS_PER_RUN;
}

const PATH_SEGMENT = /^(?:[A-Za-z_][A-Za-z0-9_-]*|[0-9]+)$/;

/** backend _check_path: dot keys and numeric indexes, 8 segments, 256 characters. */
export function isMappingPath(path: string, allowEmpty = false): boolean {
  if (path === '') return allowEmpty;
  const parts = path.split('.');
  return (
    path.length <= 256 &&
    parts.length <= 8 &&
    parts.every((p) => PATH_SEGMENT.test(p))
  );
}

/** backend _check_request_path, plus its {org_id}/{game_type} slots. */
export function isRequestPath(path: string): boolean {
  if (path.length > 2048 || !path.startsWith('/') || path.startsWith('//')) {
    return false;
  }
  const structural = path
    .replaceAll('{org_id}', '1')
    .replaceAll('{game_type}', '1');
  let decoded: string;
  try {
    decoded = decodeURIComponent(structural);
  } catch {
    return false;
  }
  return !(
    /[{}\\?#]/.test(decoded) ||
    [...decoded].some(
      (c) => c.charCodeAt(0) <= 32 || c.charCodeAt(0) === 127,
    ) ||
    decoded.startsWith('//') ||
    decoded.split('/').some((part) => part === '.' || part === '..')
  );
}

type Issue = { path: (string | number)[]; message: string };

function rowIssues(
  rows: readonly TemplateRow[],
  prefix: (string | number)[],
  { query }: { query: boolean },
): Issue[] {
  const issues: Issue[] = [];
  const seen = new Set<string>();
  rows.forEach((row, index) => {
    const at = (field: string): (string | number)[] => [
      ...prefix,
      index,
      field,
    ];
    const key = row.key.trim();
    if (!key) issues.push({ path: at('key'), message: 'Enter a field name.' });
    else if (key.length > 128 || /[{}]/.test(key)) {
      issues.push({
        path: at('key'),
        message: 'Use a plain name without braces.',
      });
    } else if (seen.has(key)) {
      issues.push({ path: at('key'), message: 'This name is already used.' });
    } else if (isSensitiveKey(key)) {
      issues.push({
        path: at('key'),
        message:
          'This name looks like a secret. Use API key field authentication for credentials.',
      });
    }
    seen.add(key);
    switch (row.kind) {
      case 'text':
        if (/\{\{|\}\}/.test(row.value)) {
          issues.push({
            path: at('value'),
            message: 'Pick a variable instead of typing braces.',
          });
        }
        break;
      case 'number':
        if (row.value.trim() === '' || !Number.isFinite(Number(row.value))) {
          issues.push({ path: at('value'), message: 'Enter a number.' });
        }
        break;
      case 'boolean':
        if (row.value !== 'true' && row.value !== 'false') {
          issues.push({ path: at('value'), message: 'Choose true or false.' });
        }
        break;
      case 'variable':
        if (!PLACEHOLDER_VALUES.includes(row.value)) {
          issues.push({ path: at('value'), message: 'Choose a variable.' });
        }
        break;
      case 'json': {
        let parsed: unknown;
        try {
          parsed = JSON.parse(row.value);
        } catch {
          issues.push({
            path: at('value'),
            message: 'This saved value is not valid.',
          });
          break;
        }
        if (query && parsed !== null && typeof parsed === 'object') {
          issues.push({
            path: at('value'),
            message: 'Query fields hold one value, not a list or object.',
          });
        }
        break;
      }
    }
  });
  return issues;
}

function credentialIssues(
  form: Pick<PushForm, 'credential_location' | 'credential_key'>,
  prefix: string,
  { required, allowBody }: { required: boolean; allowBody: boolean },
  taken: readonly TemplateRow[],
): Issue[] {
  if (form.credential_location === 'none') {
    return required
      ? [
          {
            path: [prefix, 'credential_location'],
            message: 'Choose where the API key goes.',
          },
        ]
      : [];
  }
  if (form.credential_location === 'body' && !allowBody) {
    return [
      {
        path: [prefix, 'credential_location'],
        message: 'GET requests have no body; send the key as a query field.',
      },
    ];
  }
  const key = form.credential_key.trim();
  if (!key || key.length > 128 || /[{}]/.test(key)) {
    return [
      { path: [prefix, 'credential_key'], message: 'Enter the field name.' },
    ];
  }
  if (taken.some((row) => row.key.trim() === key)) {
    return [
      {
        path: [prefix, 'credential_key'],
        message: 'Another field already uses this name.',
      },
    ];
  }
  return [];
}

export interface SyncFormContext {
  auth: OutboundAuth;
  pushEnabled: boolean;
  pullEnabled: boolean;
  memberCount: number | null | undefined;
}

export function pushIssues(form: PushForm, ctx: SyncFormContext): Issue[] {
  const issues: Issue[] = [];
  if (!isRequestPath(form.path.trim())) {
    issues.push({
      path: ['push', 'path'],
      message: 'Start with / and use only {org_id} or {game_type} as slots.',
    });
  }
  issues.push(...rowIssues(form.query, ['push', 'query'], { query: true }));
  form.query.forEach((row, index) => {
    if (row.kind === 'variable' && !PUSH_PLACEHOLDERS.includes(row.value)) {
      issues.push({
        path: ['push', 'query', index, 'value'],
        message: 'Pushes can only use the Org ID and Game type variables.',
      });
    }
  });
  if (ctx.auth === 'api_key_field') {
    issues.push(
      ...credentialIssues(
        form,
        'push',
        { required: ctx.pushEnabled, allowBody: true },
        form.query,
      ),
    );
  }
  return issues;
}

function leaves(rows: readonly TemplateRow[]): string[] {
  return rows.filter((r) => r.kind === 'variable').map((r) => r.value);
}

export function pullIssues(form: PullForm, ctx: SyncFormContext): Issue[] {
  const issues: Issue[] = [];
  if (!isRequestPath(form.path.trim())) {
    issues.push({
      path: ['pull', 'path'],
      message: 'Start with / and use only {org_id} or {game_type} as slots.',
    });
  }
  issues.push(...rowIssues(form.query, ['pull', 'query'], { query: true }));
  if (form.method === 'POST') {
    issues.push(...rowIssues(form.body, ['pull', 'body'], { query: false }));
  } else if (form.body.length > 0) {
    issues.push({
      path: ['pull', 'method'],
      message: 'GET requests have no body. Use POST or remove the body fields.',
    });
  }
  if (ctx.auth === 'api_key_field') {
    issues.push(
      ...credentialIssues(
        form,
        'pull',
        {
          required: ctx.pullEnabled || !isDefaultPull(form),
          allowBody: form.method === 'POST',
        },
        form.credential_location === 'body' ? form.body : form.query,
      ),
    );
  }
  const used = [...leaves(form.query), ...leaves(form.body)];
  const scopes = new Set(
    used.map((value) => PLACEHOLDERS.find((p) => p.value === value)?.scope),
  );
  if (scopes.has('member') && form.request_mode !== 'per_member') {
    issues.push({
      path: ['pull', 'request_mode'],
      message: "One-member variables need the 'Per member' request mode.",
    });
  }
  if (scopes.has('page') && form.pagination_kind !== 'page') {
    issues.push({
      path: ['pull', 'pagination_kind'],
      message: 'The page variable needs page-number pagination.',
    });
  }
  if (scopes.has('cursor') && form.pagination_kind !== 'cursor') {
    issues.push({
      path: ['pull', 'pagination_kind'],
      message: 'The cursor variable needs cursor pagination.',
    });
  }
  if (!isMappingPath(form.list_path.trim(), true)) {
    issues.push({ path: ['pull', 'list_path'], message: MAPPING_PATH_HELP });
  }
  if (!isMappingPath(form.player_id_path.trim())) {
    issues.push({
      path: ['pull', 'player_id_path'],
      message: MAPPING_PATH_HELP,
    });
  }
  if (!isMappingPath(form.mmr_path.trim())) {
    issues.push({ path: ['pull', 'mmr_path'], message: MAPPING_PATH_HELP });
  }
  if (form.pagination_kind === 'page') {
    if (
      !Number.isInteger(form.page_size) ||
      form.page_size < 1 ||
      form.page_size > 500
    ) {
      issues.push({
        path: ['pull', 'page_size'],
        message: 'Use a page size from 1 to 500.',
      });
    }
    if (
      form.has_more_path.trim() &&
      !isMappingPath(form.has_more_path.trim())
    ) {
      issues.push({
        path: ['pull', 'has_more_path'],
        message: MAPPING_PATH_HELP,
      });
    }
  }
  if (
    form.pagination_kind === 'cursor' &&
    !isMappingPath(form.next_cursor_path.trim())
  ) {
    issues.push({
      path: ['pull', 'next_cursor_path'],
      message: 'Enter where the next cursor is in the response.',
    });
  }
  if (
    needsPerMemberAck(form, ctx.memberCount) &&
    !form.acknowledge_per_member
  ) {
    issues.push({
      path: ['pull', 'acknowledge_per_member'],
      message: 'Confirm the request count before saving per-member mode.',
    });
  }
  return issues;
}

export const MAPPING_PATH_HELP =
  'Use dot-separated names and list positions, like data.players or items.0.rating.';

export const INTERVAL_MIN = 15;
export const INTERVAL_MAX = 10080;
