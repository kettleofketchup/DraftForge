/**
 * Sign-up records export E2E fixtures (backend tests.data.signup_records_export).
 *
 * Records Export Org (pk 62), users 9300-9305: a kept, a cancelled and a
 * deleted event, each with three signups made through the events services.
 */

import type { APIRequestContext } from '@playwright/test';
import { API_URL } from './base-url';

export interface SignupRecordsExportData {
  org_pk: number;
  staff_pk: number;
  admin_pk: number;
  member_pk: number;
  kept_event_pk: number;
  cancelled_event_pk: number;
  deleted_event_pk: number;
  deleted_event_name: string;
}

/** Rebuild the export scope (events, ledger, retention); returns its pks. */
export async function resetSignupRecordsExport(
  request: APIRequestContext,
): Promise<SignupRecordsExportData> {
  const resp = await request.post(
    `${API_URL}/tests/signup-records-export/reset/`,
  );
  if (!resp.ok()) {
    throw new Error(
      `signup-records-export reset failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json() as Promise<SignupRecordsExportData>;
}
