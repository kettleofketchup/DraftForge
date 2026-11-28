/**
 * Org API connections E2E fixtures (org-features/org-api-connections spec).
 *
 * Infrastructure (backend/tests/populate/org_api_connections.py,
 * tests.data.org_api_connections):
 * - API Connections Org: mmr_sync and promotion unlocked; two admins, staff,
 *   a member, two Steam-linked players and a member without Steam
 * - API Connections Second Org: mmr_sync unlocked; the first admin is also
 *   its admin; one seeded disabled connection with a finished pull run
 *
 * Outbound calls to the fixture's synthetic `.test` origins are answered by
 * the backend's test-only fake transport (tests.helpers.
 * org_api_connections_transport): these specs never reach a real service.
 * driveOrgApiConnections runs the due runs and deliveries through the real
 * step services instead of waiting for the beat sweep.
 *
 * Never hardcode PKs: read them from resetOrgApiConnections.
 */

import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
} from '@playwright/test';

import { API_URL } from './base-url';
import { orgFeaturesApi } from './org-features';

export type OrgApiConnectionsRole =
  | 'admin'
  | 'admin_two'
  | 'staff'
  | 'member'
  | 'second_admin';

export interface OrgApiConnectionsTestData {
  orgs: Record<'main' | 'second', { pk: number; name: string }>;
  users: Record<OrgApiConnectionsRole, { pk: number; username: string }>;
  players: {
    one: { pk: number; steam_id: number; mmr: number };
    two: { pk: number; steam_id: number; mmr: number };
    no_steam: { pk: number };
  };
  fake: {
    origin: string;
    moved_origin: string;
    good_credential: string;
    bad_credential: string;
    pull_path: string;
  };
  seeded_connection: number;
}

export interface FakeCall {
  method: string;
  host: string;
  path: string;
  status: number;
  mmrs?: number[];
}

export interface OrgApiConnectionsState {
  mmrs: Record<string, number>;
  deliveries: {
    connection_id: number;
    state: string;
    last_reason: string;
    destination_origin: string;
  }[];
  calls: FakeCall[];
}

export interface ConnectionRow {
  id: number;
  config_version: number;
  enabled: boolean;
  inbound_enabled: boolean;
  mmr_push_enabled: boolean;
  mmr_pull_enabled: boolean;
  operations: string[];
  credential_present: boolean;
  interval_minutes: number | null;
  next_due_at: string | null;
  [key: string]: unknown;
}

async function json<T>(resp: APIResponse, what: string): Promise<T> {
  if (!resp.ok()) {
    throw new Error(
      `${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`,
    );
  }
  return (await resp.json()) as T;
}

/** Recreate the orgs, users, roles and seed; drop every connection row. */
export async function resetOrgApiConnections(
  request: APIRequestContext,
): Promise<OrgApiConnectionsTestData> {
  return json(
    await request.post(`${API_URL}/tests/org-api-connections/reset/`),
    'org-api-connections reset',
  );
}

/** Log in as an API connections test user (the context's cookies hold the session). */
export async function loginOrgApiConnections(
  context: BrowserContext,
  role: OrgApiConnectionsRole,
): Promise<void> {
  await json(
    await context.request.post(
      `${API_URL}/tests/login-org-api-connections/${role}/`,
    ),
    `login-org-api-connections ${role}`,
  );
}

/** Run the fixture orgs' due runs and deliveries now. */
export async function driveOrgApiConnections(
  request: APIRequestContext,
  editAfterStage?: { user_pk: number; mmr: number },
): Promise<{ steps: number }> {
  return json(
    await request.post(`${API_URL}/tests/org-api-connections/drive/`, {
      data: editAfterStage ? { edit_after_stage: editAfterStage } : {},
    }),
    'org-api-connections drive',
  );
}

/** Member MMRs, delivery states and the fake transport's call log. */
export async function orgApiConnectionsState(
  request: APIRequestContext,
): Promise<OrgApiConnectionsState> {
  return json(
    await request.get(`${API_URL}/tests/org-api-connections/state/`),
    'org-api-connections state',
  );
}

/** Seed an adopted promotion stream connection holding a held backlog. */
export async function seedPromotionBacklog(
  request: APIRequestContext,
): Promise<{ connection_id: number }> {
  return json(
    await request.post(
      `${API_URL}/tests/org-api-connections/promotion-backlog/`,
    ),
    'org-api-connections promotion backlog',
  );
}

/** Session-authenticated call to the org's connection management API. */
export async function connectionApi<T = unknown>(
  context: BrowserContext,
  orgPk: number,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  data?: Record<string, unknown>,
): Promise<T> {
  return orgFeaturesApi<T>(
    context,
    method,
    `/organizations/${orgPk}/api-connections/${path}`,
    data,
  );
}

/** Call an inbound endpoint with a connection key (no session cookies). */
export async function machineRequest(
  request: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  token: string,
  body?: Record<string, unknown>,
): Promise<APIResponse> {
  const url = `${API_URL}${path}`;
  const headers = { Authorization: `Bearer ${token}` };
  return method === 'GET'
    ? request.get(url, { headers })
    : request.post(url, { headers, data: body ?? {} });
}
