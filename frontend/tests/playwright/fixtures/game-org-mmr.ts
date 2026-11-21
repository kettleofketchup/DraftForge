/**
 * Per-game org MMR E2E fixtures (backend tests.data.game_org_mmr).
 *
 * Game MMR Org / League (pk 50), users 8000-8007, a Dota tournament and a
 * Deadlock tournament created from a Deadlock event.
 */

import type { BrowserContext } from '@playwright/test';
import { API_URL } from './base-url';

export const GAME_TYPE_DOTA2 = 1;
export const GAME_TYPE_DEADLOCK = 2;

interface Named {
  pk: number;
  name: string;
}

interface SeededUser {
  pk: number;
  username: string;
}

export interface GameOrgMmrData {
  org: Named;
  league: Named;
  tournaments: { dota: Named; deadlock: Named };
  events: { deadlock: Named };
  users: {
    players: SeededUser[];
    display: SeededUser;
    edit: SeededUser;
    approve: SeededUser;
  };
}

export interface DeadlockApproveSetup {
  org_pk: number;
  event_pk: number;
  signup_pk: number;
  user_pk: number;
  dota_mmr: number;
}

export interface OrgMembership {
  org_users: {
    pk: number;
    organization_pk: number;
    mmr: number;
    game_mmrs: Record<string, number>;
  }[];
}

async function json<T>(
  resp: import('@playwright/test').APIResponse,
  what: string,
): Promise<T> {
  if (!resp.ok()) {
    throw new Error(`${what} failed: ${resp.status()} ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

/** The seeded per-game org MMR entities. */
export async function getGameOrgMmrData(
  context: BrowserContext,
): Promise<GameOrgMmrData> {
  return json(
    await context.request.get(`${API_URL}/tests/game-org-mmr/data/`),
    'game-org-mmr data (run just db::populate::all)',
  );
}

/**
 * Rebuild the Deadlock approve event with a fresh pending signup for the
 * approve user: Dota MMR back to its baseline, no Deadlock MMR, and the
 * Deadlock profile rank re-asserted.
 */
export async function setupDeadlockApprove(
  context: BrowserContext,
): Promise<DeadlockApproveSetup> {
  return json(
    await context.request.post(`${API_URL}/tests/game-org-mmr/approve-setup/`),
    'game-org-mmr approve-setup',
  );
}

/** The test endpoint membership dump (OrgUser rows with game_mmrs). */
export async function getOrgMembership(
  context: BrowserContext,
  userPk: number,
): Promise<OrgMembership> {
  return json(
    await context.request.get(
      `${API_URL}/tests/user/${userPk}/org-membership/`,
    ),
    'org-membership',
  );
}
