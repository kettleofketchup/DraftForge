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

import {
  expect,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
  type Page,
} from '@playwright/test';

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
    throw new Error(
      `${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`,
    );
  }
  return (await resp.json()) as T;
}

export async function getOrgFeaturesData(
  request: APIRequestContext,
): Promise<OrgFeaturesTestData> {
  return json(
    await request.get(`${API_URL}/tests/org-features/data/`),
    'org-features data',
  );
}

/** Rebuild ledger, promo sends, point values, events, templates, switches and roles. */
export async function resetOrgFeatures(
  request: APIRequestContext,
): Promise<OrgFeaturesTestData> {
  return json(
    await request.post(`${API_URL}/tests/org-features/reset/`),
    'org-features reset',
  );
}

/** Log in as an org features test user (the context's cookies hold the session). */
export async function loginOrgFeatures(
  context: BrowserContext,
  role: OrgFeaturesRole,
): Promise<void> {
  await json(
    await context.request.post(`${API_URL}/tests/login-org-features/${role}/`),
    `login-org-features ${role}`,
  );
}

async function csrfHeaders(
  context: BrowserContext,
): Promise<Record<string, string>> {
  const csrf = (await context.cookies()).find((c) => isCsrfCookie(c.name));
  return {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrf?.value ?? '',
  };
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
    throw new Error(
      `${method} ${path} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`,
    );
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
export async function moveEventToRollCall(
  context: BrowserContext,
  eventPk: number,
): Promise<void> {
  await orgFeaturesApi(context, 'POST', `/events/${eventPk}/open_signups/`);
  await orgFeaturesApi(context, 'POST', `/events/${eventPk}/start_roll_call/`);
}

/**
 * Assert no "Session expired" toast fired. `networkidle` only settles a navigation load,
 * so callers that trigger in-page refetches (e.g. logout without reload) must await those
 * responses first. Over the hold window the interceptor's synchronous flag (set before
 * sonner's dynamic import) and the toast count are both checked on every tick and once
 * more at the end, so a late 401/403 still fails the test.
 */
export async function expectNoSessionToast(
  page: Page,
  holdMs = 2000,
): Promise<void> {
  await page.waitForLoadState('networkidle');
  const toast = page.getByText(/Session expired/);
  const assertClean = async (): Promise<void> => {
    const flagged = await page.evaluate(
      () =>
        (window as unknown as Record<string, unknown>)._auth_toast_shown ===
        true,
    );
    expect(
      flagged,
      'axios interceptor flagged a session-expired response',
    ).toBe(false);
    expect(await toast.count(), 'Session expired toast is visible').toBe(0);
  };
  const deadline = Date.now() + holdMs;
  while (Date.now() < deadline) {
    await assertClean();
    await page.waitForTimeout(250);
  }
  await assertClean();
}
