/**
 * Event E2E test fixtures.
 *
 * Infrastructure (created by populate_events_data; pks from
 * GET /api/tests/events/data/):
 * - Events Test Org - dedicated org
 * - Events Test League and Events Test League B - under Events org
 * - E2E Signup Event - standalone event in signups_open state
 * - Weekly Inhouse - EventRepeater for generation tests
 * - Users: event_org_admin (org admin), event_player_1, event_player_4
 *   (rank_status="never", battle_cup_tier=5), event_player_no_profile
 */

import type { BrowserContext } from '@playwright/test';
import { API_URL } from './base-url';
import { isCsrfCookie } from './cookies';

export const EVENTS_ORG_NAME = 'Events Test Org';
export const EVENTS_EVENT_NAME = 'E2E Signup Event';

/** Extract CSRF token from context cookies. Must be called after login. */
export async function getCsrfToken(context: BrowserContext): Promise<string> {
  const cookies = await context.cookies();
  const csrf = cookies.find((c) => isCsrfCookie(c.name));
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

export interface EventsTestData {
  org_pk: number;
  event_pk: number;
  events_league_pk: number;
  alt_league_pk: number;
  alt_league_name: string;
  users: {
    admin: number;
    player: number;
    player_4: number;
    no_profile: number;
  };
}

/** The seeded events pks, looked up by name on the backend. */
export async function getEventsSeedData(
  context: BrowserContext,
): Promise<EventsTestData> {
  const resp = await context.request.get(`${API_URL}/tests/events/data/`);
  if (!resp.ok()) {
    throw new Error(
      `events data (run just db::populate::all) failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json() as Promise<EventsTestData>;
}

export interface EventInfo {
  pk: number;
  orgPk: number;
  leaguePk: number;
  name: string;
  state: string;
  /** The events test league; stays put even if the seeded event swaps leagues. */
  eventsLeaguePk: number;
  /** "Events Test League B", the same-org swap target. */
  altLeaguePk: number;
  /** Name of the secondary league. */
  altLeagueName: string;
}

/** The seeded Events Test Org and E2E Signup Event, with its live state. */
export async function getEventsTestData(
  context: BrowserContext,
): Promise<EventInfo> {
  const seed = await getEventsSeedData(context);
  const resp = await context.request.get(`${API_URL}/events/${seed.event_pk}/`);
  if (!resp.ok()) {
    throw new Error(
      `${EVENTS_EVENT_NAME} fetch failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  const event = await resp.json();

  return {
    pk: seed.event_pk,
    orgPk: seed.org_pk,
    leaguePk: event.tournament_league,
    name: event.name,
    state: event.state,
    eventsLeaguePk: seed.events_league_pk,
    altLeaguePk: seed.alt_league_pk,
    altLeagueName: seed.alt_league_name,
  };
}

/** Reset events data to clean state via backend test endpoint. */
export async function resetEventsData(context: BrowserContext): Promise<void> {
  const resp = await context.request.post(`${API_URL}/tests/events/reset/`);
  if (!resp.ok()) {
    throw new Error(`Events reset failed: ${resp.status()}`);
  }
}

async function loginEventUser(
  context: BrowserContext,
  role: keyof EventsTestData['users'],
  label: string,
) {
  const { users } = await getEventsSeedData(context);
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: users[role] },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login ${label} failed: ${resp.status()}`);
  return resp.json();
}

/** Login as the dedicated event org admin. */
export async function loginEventAdmin(context: BrowserContext) {
  return loginEventUser(context, 'admin', 'event admin');
}

/** Trigger event generation synchronously (calls the Celery task directly). */
export async function triggerEventGeneration(
  context: BrowserContext,
): Promise<string> {
  const resp = await context.request.post(`${API_URL}/tests/events/generate/`);
  if (!resp.ok()) {
    throw new Error(`Event generation trigger failed: ${resp.status()}`);
  }
  const data = await resp.json();
  return data.message;
}

/** Login as event_player_1. */
export async function loginEventPlayer(context: BrowserContext) {
  return loginEventUser(context, 'player', 'event player');
}

/** Login as event_player_4 (rank_status="never", battle_cup_tier=5). */
export async function loginEventPlayer4(context: BrowserContext) {
  return loginEventUser(context, 'player_4', 'event player 4');
}

/**
 * TEST: Set the org MMR of (orgPk, userPk) for one game (default Dota 2).
 * 0 clears it. Invalidates cacheops.
 */
export async function setApprovedMmr(
  context: BrowserContext,
  orgPk: number,
  userPk: number,
  mmr: number,
  gameType?: number,
) {
  const resp = await context.request.post(
    `${API_URL}/tests/org/${orgPk}/user/${userPk}/set-approved-mmr/`,
    {
      data: gameType == null ? { mmr } : { mmr, game_type: gameType },
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!resp.ok()) {
    throw new Error(
      `setApprovedMmr failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json();
}

/** Login as event_player_no_profile (no PlayerDotaProfile). */
export async function loginEventPlayerNoProfile(context: BrowserContext) {
  return loginEventUser(context, 'no_profile', 'event_player_no_profile');
}

/** Whether the backend has a Discord bot token; without one nothing posts. */
export async function discordBotConfigured(
  context: BrowserContext,
): Promise<boolean> {
  const resp = await context.request.get(`${API_URL}/tests/discord/status/`);
  if (!resp.ok()) {
    throw new Error(
      `Discord status check failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  const data = await resp.json();
  return data.bot_token_configured === true;
}

/** Trigger sync_discord_events synchronously. */
export async function syncDiscordEvents(
  context: BrowserContext,
): Promise<string> {
  const resp = await context.request.post(
    `${API_URL}/tests/events/sync-discord/`,
  );
  if (!resp.ok()) {
    throw new Error(
      `Discord sync trigger failed: ${resp.status()} ${await resp.text()}`,
    );
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
  const resp = await context.request.get(
    `${API_URL}/tests/events/${eventId}/discord-verify/`,
  );
  return resp.json();
}
