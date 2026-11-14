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
