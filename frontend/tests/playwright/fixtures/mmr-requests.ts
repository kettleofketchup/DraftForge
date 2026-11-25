/**
 * MMR update request E2E fixtures (backend tests.data.mmr_requests).
 *
 * MMR Requests Org / League (pk 60). Members 8200-8202 start at an unverified
 * 4200 org (Dota) and league MMR; 8203 is org staff, 8204 league staff, 8205
 * an outsider. Read PKs from getMmrRequestsData, never hardcode them.
 */

import type { APIResponse, BrowserContext } from '@playwright/test';
import { fileURLToPath } from 'node:url';

import { API_URL } from './base-url';

export const MMR_SCREENSHOT_PATH: string = fileURLToPath(
  new URL('./images/mmr-screenshot.png', import.meta.url),
);

interface Named {
  pk: number;
  name: string;
}

export interface MmrRequestsUser {
  pk: number;
  username: string;
  nickname: string;
  org_user_pk: number | null;
  league_user_pk: number | null;
}

export type MmrRequestsRole =
  | 'member_approve'
  | 'member_reject'
  | 'member_staffset'
  | 'org_staff'
  | 'league_staff'
  | 'outsider';

export interface MmrRequestsData {
  org: Named;
  league: Named;
  base_mmr: number;
  game_types: { dota2: number; deadlock: number; league: number };
  users: Record<MmrRequestsRole, MmrRequestsUser>;
}

export interface ResetMmrRequestsOptions {
  /** Make the org member list private (it is reset to public otherwise). */
  membersPrivate?: boolean;
}

async function json<T>(resp: APIResponse, what: string): Promise<T> {
  if (!resp.ok()) {
    throw new Error(
      `${what} failed: ${resp.status()} ${(await resp.text()).slice(0, 300)}`,
    );
  }
  return (await resp.json()) as T;
}

/** The seeded MMR request org, league and users. */
export async function getMmrRequestsData(
  context: BrowserContext,
): Promise<MmrRequestsData> {
  return json(
    await context.request.get(`${API_URL}/tests/mmr-requests/data/`),
    'mmr-requests data (run just db::populate::all)',
  );
}

/**
 * Delete a member's requests and screenshots and restore their unverified
 * 4200 org and league MMR.
 */
export async function resetMmrRequests(
  context: BrowserContext,
  userPk: number,
  options: ResetMmrRequestsOptions = {},
): Promise<void> {
  const params = new URLSearchParams({ user: String(userPk) });
  if (options.membersPrivate) params.set('members_private', '1');
  await json(
    await context.request.post(
      `${API_URL}/tests/mmr-requests/reset/?${params.toString()}`,
    ),
    'mmr-requests reset',
  );
}
