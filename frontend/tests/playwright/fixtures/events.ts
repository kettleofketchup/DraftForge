/**
 * Event E2E test fixtures.
 *
 * Infrastructure (created by populate_events_data):
 * - Events Test Org (pk=7) - dedicated org
 * - Events Test League (steam_league_id=17935) - under Events org
 * - E2E Signup Event - standalone event in signups_open state
 * - Weekly Inhouse - EventRepeater for generation tests
 *
 * Test users:
 * - event_org_admin (pk=5000) - org admin
 * - event_player_1 (pk=5001) - regular player
 * - event_player_2 (pk=5002) - regular player
 * - event_player_3 (pk=5003) - regular player
 */

import type { BrowserContext } from '@playwright/test';

const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
const API_URL = `https://${DOCKER_HOST}/api`;

export const EVENTS_ORG_NAME = 'Events Test Org';
export const EVENTS_EVENT_NAME = 'E2E Signup Event';

/** Extract CSRF token from context cookies. Must be called after login. */
export async function getCsrfToken(context: BrowserContext): Promise<string> {
  const cookies = await context.cookies();
  const csrf = cookies.find((c) => c.name === 'csrftoken');
  return csrf?.value || '';
}

/** POST with CSRF token header (required for DRF SessionAuthentication). */
export async function postWithCsrf(
  context: BrowserContext,
  url: string,
  data?: Record<string, unknown>,
): Promise<import('@playwright/test').APIResponse> {
  const csrfToken = await getCsrfToken(context);
  return context.request.post(url, {
    data,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
  });
}

/** PATCH with CSRF token header. */
export async function patchWithCsrf(
  context: BrowserContext,
  url: string,
  data?: Record<string, unknown>,
): Promise<import('@playwright/test').APIResponse> {
  const csrfToken = await getCsrfToken(context);
  return context.request.patch(url, {
    data,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
  });
}

export interface EventInfo {
  pk: number;
  orgPk: number;
  leaguePk: number;
  name: string;
  state: string;
  /** Stable PK of the events test league (pk=7) — does not change even if the seeded event swaps leagues. */
  eventsLeaguePk: number;
  /** PK of the secondary "Events Test League B" (pk=8) — used as the same-org swap target. */
  altLeaguePk: number;
  /** Name of the secondary league. */
  altLeagueName: string;
}

/** Look up the Events Test Org and E2E Signup Event by name. */
export async function getEventsTestData(context: BrowserContext): Promise<EventInfo> {
  // Find org
  const orgsResp = await context.request.get(`${API_URL}/organizations/`);
  const orgs = await orgsResp.json();
  const eventsOrg = orgs.find((o: { name: string }) => o.name === EVENTS_ORG_NAME);
  if (!eventsOrg) throw new Error(`${EVENTS_ORG_NAME} not found. Run just db::populate::all`);

  // Find event
  const eventsResp = await context.request.get(`${API_URL}/events/?organization=${eventsOrg.pk}`);
  const events = await eventsResp.json();
  const signupEvent = events.find((e: { name: string }) => e.name === EVENTS_EVENT_NAME);
  if (!signupEvent) throw new Error(`${EVENTS_EVENT_NAME} not found. Run just db::populate::all`);

  return {
    pk: signupEvent.id,
    orgPk: eventsOrg.pk,
    leaguePk: signupEvent.tournament_league,
    name: signupEvent.name,
    state: signupEvent.state,
    eventsLeaguePk: 7,
    altLeaguePk: 8,
    altLeagueName: 'Events Test League B',
  };
}

/** Reset events data to clean state via backend test endpoint. */
export async function resetEventsData(context: BrowserContext): Promise<void> {
  const resp = await context.request.post(`${API_URL}/tests/events/reset/`);
  if (!resp.ok()) {
    throw new Error(`Events reset failed: ${resp.status()}`);
  }
}

/** Login as the dedicated event org admin (pk=5000). */
export async function loginEventAdmin(context: BrowserContext) {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: 5000 },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login event admin failed: ${resp.status()}`);
  return resp.json();
}

/** Trigger event generation synchronously (calls the Celery task directly). */
export async function triggerEventGeneration(context: BrowserContext): Promise<string> {
  const resp = await context.request.post(`${API_URL}/tests/events/generate/`);
  if (!resp.ok()) {
    throw new Error(`Event generation trigger failed: ${resp.status()}`);
  }
  const data = await resp.json();
  return data.message;
}

/** Login as an event player (pk=5001). */
export async function loginEventPlayer(context: BrowserContext) {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: 5001 },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login event player failed: ${resp.status()}`);
  return resp.json();
}

/** Trigger sync_discord_events synchronously. */
export async function syncDiscordEvents(context: BrowserContext): Promise<string> {
  const resp = await context.request.post(`${API_URL}/tests/events/sync-discord/`);
  if (!resp.ok()) {
    throw new Error(`Discord sync trigger failed: ${resp.status()}`);
  }
  const data = await resp.json();
  return data.message;
}

/** Simulate a Discord signup via backend test endpoint. */
export async function simulateDiscordSignup(
  context: BrowserContext,
  eventId: number,
  data: {
    discord_user_id: string;
    discord_username: string;
    rank_status: string;
    rank_medal?: string;
    battle_cup_tier?: number;
    positions?: string[];
    friend_id?: string;
  },
): Promise<import('@playwright/test').APIResponse> {
  return context.request.post(
    `${API_URL}/tests/events/${eventId}/discord-signup/`,
    { data, headers: { 'Content-Type': 'application/json' } },
  );
}

/** Send a test notification DM to a specific Discord user. */
export async function sendTestNotification(
  context: BrowserContext,
  eventId: number,
  discordUserId: string,
): Promise<import('@playwright/test').APIResponse> {
  return context.request.post(
    `${API_URL}/tests/events/${eventId}/send-notification/`,
    {
      data: { discord_user_id: discordUserId },
      headers: { 'Content-Type': 'application/json' },
    },
  );
}

/** Verify Discord messages for an event. */
export async function verifyDiscordMessages(
  context: BrowserContext,
  eventId: number,
) {
  const resp = await context.request.get(`${API_URL}/tests/events/${eventId}/discord-verify/`);
  return resp.json();
}
