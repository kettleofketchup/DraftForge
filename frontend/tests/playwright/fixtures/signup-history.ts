/**
 * Signup history E2E fixtures (backend tests.data.signup_history).
 *
 * Signup History Org (pk 60), users 9000-9006 and "Signup History Event",
 * whose signups were made through the events services so the ledger has
 * real entries.
 */

import type { BrowserContext } from '@playwright/test';
import { API_URL } from './base-url';

export interface SignupHistoryData {
  org_pk: number;
  event_pk: number;
  staff_pk: number;
  outsider_pk: number;
  member_pks: number[];
  withdrawer_pk: number;
  promoted_pk: number;
  staff_added_pk: number;
  long_nick_pk: number;
  discord_button_pk: number;
  reaction_pk: number;
}

/** The seeded signup history pks, by role. */
export async function getSignupHistoryData(
  context: BrowserContext,
): Promise<SignupHistoryData> {
  const resp = await context.request.get(
    `${API_URL}/tests/signup-history/data/`,
  );
  if (!resp.ok()) {
    throw new Error(
      `signup-history data (run just db::populate::all) failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json() as Promise<SignupHistoryData>;
}

/** Rebuild the signup history event and its ledger; returns the new pks. */
export async function resetSignupHistoryData(
  context: BrowserContext,
): Promise<SignupHistoryData> {
  const resp = await context.request.post(
    `${API_URL}/tests/signup-history/reset/`,
  );
  if (!resp.ok()) {
    throw new Error(
      `signup-history reset failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json() as Promise<SignupHistoryData>;
}
