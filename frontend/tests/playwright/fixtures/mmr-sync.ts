/**
 * MMR sync API E2E fixtures (19-org-features/13-mmr-sync-api spec).
 *
 * Infrastructure (backend/tests/populate/mmr_sync.py, tests.data.mmr_sync):
 * - MMR Sync Org: mmr_sync unlocked; admin, staff, member and a Steam-linked player
 * - MMR Sync Locked Org: mmr_sync locked; its own admin
 *
 * Never hardcode PKs: read them from resetMmrSync.
 */

import type {
  APIRequestContext,
  APIResponse,
  BrowserContext,
} from '@playwright/test';

import { API_URL } from './base-url';

export type MmrSyncRole =
  | 'admin'
  | 'staff'
  | 'member'
  | 'player'
  | 'locked_admin';

export interface MmrSyncTestData {
  orgs: Record<'unlocked' | 'locked', { pk: number; name: string }>;
  users: Record<MmrSyncRole, { pk: number; username: string }>;
  player: { pk: number; steam_id: number; mmr: number };
}

async function json<T>(resp: APIResponse, what: string): Promise<T> {
  if (!resp.ok()) {
    throw new Error(
      `${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`,
    );
  }
  return (await resp.json()) as T;
}

/** Recreate the orgs, users, roles and switches; drop tokens, usage and limits. */
export async function resetMmrSync(
  request: APIRequestContext,
): Promise<MmrSyncTestData> {
  return json(
    await request.post(`${API_URL}/tests/mmr-sync/reset/`),
    'mmr-sync reset',
  );
}

/** Log in as an MMR sync test user (the context's cookies hold the session). */
export async function loginMmrSync(
  context: BrowserContext,
  role: MmrSyncRole,
): Promise<void> {
  await json(
    await context.request.post(`${API_URL}/tests/login-mmr-sync/${role}/`),
    `login-mmr-sync ${role}`,
  );
}

/** Call the token-authenticated mmr-sync endpoint (no session cookies). */
export async function mmrSyncRequest(
  request: APIRequestContext,
  orgPk: number,
  token: string,
  body?: Record<string, unknown>,
): Promise<APIResponse> {
  const url = `${API_URL}/organizations/${orgPk}/mmr-sync/`;
  const headers = { Authorization: `Bearer ${token}` };
  return body === undefined
    ? request.get(url, { headers })
    : request.post(url, { headers, data: body });
}
