import type {
  ApiConnection,
  ConnectionCredential,
  ConnectionRun,
} from '../connectionSchemas';

export const RAW_KEY = 'dfk_feedbeef_onlyshownonce';

export function connectionCredential(
  overrides: Partial<ConnectionCredential> = {},
): ConnectionCredential {
  return {
    id: 31,
    prefix: 'feedbeef',
    user_id: 9,
    issued_by_id: 9,
    operations: ['mmr:read'],
    created_at: '2026-11-20T10:00:00Z',
    revoked_at: null,
    ...overrides,
  };
}

/** A wire row as the backend's ConnectionSerializer sends it. */
export function apiConnection(
  overrides: Partial<ApiConnection> = {},
): ApiConnection {
  return {
    id: 12,
    config_version: 1,
    name: 'Ratings service',
    enabled: false,
    inbound_enabled: false,
    mmr_push_enabled: false,
    mmr_pull_enabled: false,
    promotion_push_enabled: false,
    operations: [],
    outbound_base_url: '',
    outbound_auth: 'none',
    mmr_push_config: {
      path: '/api/v1/organizations/{org_id}/mmr',
      query: {},
      body: null,
      credential_field: null,
    },
    mmr_pull_config: {
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
    },
    game_type: null,
    overwrite_policy: 'missing_only',
    mark_verified: false,
    interval_minutes: null,
    created_at: '2026-11-20T09:00:00Z',
    updated_at: '2026-11-20T09:00:00Z',
    archived_at: null,
    created_by: 9,
    updated_by: 9,
    credential_present: false,
    outbound_credential_owner: null,
    outbound_authorizer: null,
    outbound_credential_set_at: null,
    inbound_credentials: [],
    legacy_multi_credential: false,
    last_run_summary: null,
    last_success_at: null,
    last_error_code: '',
    next_due_at: null,
    promotion_stream: false,
    ...overrides,
  };
}

/** The raw wire body, where an empty summary is `{}`. */
export function apiConnectionWire(
  overrides: Partial<ApiConnection> = {},
): Record<string, unknown> {
  const row = apiConnection(overrides);
  return {
    ...row,
    last_run_summary: row.last_run_summary ?? {},
  };
}

export function connectionRun(
  overrides: Partial<ConnectionRun> = {},
): ConnectionRun {
  return {
    id: '7d2f8a64-2f5b-4c1e-9c3e-111111111111',
    kind: 'mmr_pull',
    state: 'succeeded',
    config_version: 3,
    created_at: '2026-11-20T10:00:00Z',
    started_at: '2026-11-20T10:00:01Z',
    finished_at: '2026-11-20T10:00:05Z',
    error_code: '',
    request_count: 1,
    row_count: 20,
    response_bytes: 2048,
    updated_count: 18,
    unchanged_count: 1,
    unmatched_count: 1,
    invalid_count: 0,
    conflict_count: 0,
    skipped_policy_count: 0,
    missing_identifier_count: 0,
    verified_count: 0,
    issue_count: 1,
    requester: 9,
    trigger: 'manual',
    direction: null,
    health_only: false,
    worker_status: null,
    ...overrides,
  };
}

/** Every browser storage the environment provides, as text. */
export function browserStorageText(): string {
  const stores = [globalThis.localStorage, globalThis.sessionStorage].filter(
    (store): store is Storage => store != null,
  );
  return JSON.stringify(stores.map((store) => ({ ...store })));
}

export function clearBrowserStorage(): void {
  globalThis.localStorage?.clear();
  globalThis.sessionStorage?.clear();
}
