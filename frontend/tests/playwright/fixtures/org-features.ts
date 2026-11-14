/**
 * Org paid features E2E fixtures (19-org-features specs).
 *
 * Infrastructure (backend/tests/populate/org_features.py, tests.data.org_features):
 * - Features Test Org: contributions and promotion unlocked, public members
 * - Locked Features Org: both features locked
 * - Private Features Org: both unlocked, members private
 *
 * Never hardcode PKs: read them from getOrgFeaturesData / resetOrgFeatures.
 */

import type { APIRequestContext, APIResponse, BrowserContext } from '@playwright/test';

import { API_URL } from './base-url';
import { isCsrfCookie } from './cookies';

export type OrgFeaturesRole =
  | 'owner'
  | 'admin'
  | 'staff'
  | 'promoter'
  | 'member'
  | 'outsider'
  | 'locked_admin'
  | 'private_member';

export interface OrgFeaturesRef {
  pk: number;
  name: string;
}

export interface OrgFeaturesEvent {
  pk: number;
  name: string;
  state: string;
}

export interface OrgFeaturesTestData {
  orgs: Record<'features' | 'locked' | 'private', OrgFeaturesRef>;
  users: Record<OrgFeaturesRole, { pk: number; username: string }>;
  events: Record<'upcoming' | 'upcoming2' | 'completed', OrgFeaturesEvent>;
  templates: { pk: number; name: string; org_pk: number }[];
  tournaments: OrgFeaturesRef[];
}

async function json<T>(resp: APIResponse, what: string): Promise<T> {
  if (!resp.ok()) {
    throw new Error(`${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`);
  }
  return (await resp.json()) as T;
}

export async function getOrgFeaturesData(request: APIRequestContext): Promise<OrgFeaturesTestData> {
  return json(await request.get(`${API_URL}/tests/org-features/data/`), 'org-features data');
}

/** Rebuild ledger, promo sends, point values, events, templates, switches and roles. */
export async function resetOrgFeatures(request: APIRequestContext): Promise<OrgFeaturesTestData> {
  return json(await request.post(`${API_URL}/tests/org-features/reset/`), 'org-features reset');
}

/** Log in as an org features test user (the context's cookies hold the session). */
export async function loginOrgFeatures(context: BrowserContext, role: OrgFeaturesRole): Promise<void> {
  await json(
    await context.request.post(`${API_URL}/tests/login-org-features/${role}/`),
    `login-org-features ${role}`,
  );
}

async function csrfHeaders(context: BrowserContext): Promise<Record<string, string>> {
  const csrf = (await context.cookies()).find((c) => isCsrfCookie(c.name));
  return { 'Content-Type': 'application/json', 'X-CSRFToken': csrf?.value ?? '' };
}

/** A same-session API call with the CSRF header; throws on a non-2xx answer. */
export async function orgFeaturesApi<T = unknown>(
  context: BrowserContext,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  data?: Record<string, unknown>,
): Promise<T> {
  const resp = await context.request.fetch(`${API_URL}${path}`, {
    method,
    data,
    headers: await csrfHeaders(context),
  });
  if (!resp.ok()) {
    throw new Error(`${method} ${path} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`);
  }
  return (resp.status() === 204 ? undefined : await resp.json()) as T;
}

export interface LeaderboardRowRef {
  org_user_pk: number;
  user_pk: number;
  points: number;
}

/** The viewer's all-time leaderboard rows for an org, keyed by user pk. */
export async function leaderboardByUser(
  context: BrowserContext,
  orgPk: number,
): Promise<Map<number, LeaderboardRowRef>> {
  const body = await orgFeaturesApi<{ rows: LeaderboardRowRef[] }>(
    context,
    'GET',
    `/organizations/${orgPk}/contributions/leaderboard/`,
  );
  return new Map(body.rows.map((row) => [row.user_pk, row]));
}

/** Move an upcoming event to roll call (open signups, then start roll call). */
export async function moveEventToRollCall(context: BrowserContext, eventPk: number): Promise<void> {
  await orgFeaturesApi(context, 'POST', `/events/${eventPk}/open_signups/`);
  await orgFeaturesApi(context, 'POST', `/events/${eventPk}/start_roll_call/`);
}
