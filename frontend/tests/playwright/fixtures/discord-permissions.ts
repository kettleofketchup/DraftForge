import type { BrowserContext } from '@playwright/test';
import { API_URL } from './base-url';
import { postWithCsrf } from './events';

export interface DiscordPermissionsData {
  org_pk: number;
  league_pk: number;
  fresh_event_pk: number;
  posted_event_pk: number;
  staff_pk: number;
  league_staff_pk: number;
  outsider_pk: number;
  channel_ids: {
    announcement: string;
    attendance: string;
    historical_thread: string;
  };
  message_log_count: number;
}

export type DiscordPermissionScenario =
  | 'all_granted'
  | 'attendance_missing_embed'
  | 'no_create_events'
  | 'edit_access_denied'
  | 'upstream_unavailable';

export async function getDiscordPermissionsData(
  context: BrowserContext,
): Promise<DiscordPermissionsData> {
  const response = await context.request.get(
    `${API_URL}/tests/discord-permissions/data/`,
  );
  if (!response.ok())
    throw new Error(
      `Permission data: ${response.status()} ${await response.text()}`,
    );
  return response.json();
}

export async function resetDiscordPermissions(
  context: BrowserContext,
): Promise<DiscordPermissionsData> {
  const response = await postWithCsrf(
    context,
    `${API_URL}/tests/discord-permissions/reset/`,
  );
  if (!response.ok())
    throw new Error(
      `Permission reset: ${response.status()} ${await response.text()}`,
    );
  return response.json();
}

export async function setDiscordPermissionScenario(
  context: BrowserContext,
  scenario: DiscordPermissionScenario,
): Promise<DiscordPermissionsData> {
  const response = await postWithCsrf(
    context,
    `${API_URL}/tests/discord-permissions/scenario/`,
    { scenario },
  );
  if (!response.ok())
    throw new Error(
      `Permission scenario: ${response.status()} ${await response.text()}`,
    );
  return response.json();
}
