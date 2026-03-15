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
 * - event_org_admin (pk=1080) - org admin
 * - event_player_1 (pk=1081) - regular player
 * - event_player_2 (pk=1082) - regular player
 * - event_player_3 (pk=1083) - regular player
 */

import type { BrowserContext } from '@playwright/test';

const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
const API_URL = `https://${DOCKER_HOST}/api`;

export const EVENTS_ORG_NAME = 'Events Test Org';
export const EVENTS_EVENT_NAME = 'E2E Signup Event';

export interface EventInfo {
  pk: number;
  orgPk: number;
  name: string;
  state: string;
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
    name: signupEvent.name,
    state: signupEvent.state,
  };
}

/** Reset events data to clean state via backend test endpoint. */
export async function resetEventsData(context: BrowserContext): Promise<void> {
  const resp = await context.request.post(`${API_URL}/tests/events/reset/`);
  if (!resp.ok()) {
    throw new Error(`Events reset failed: ${resp.status()}`);
  }
}

/** Login as the dedicated event org admin (pk=1080). */
export async function loginEventAdmin(context: BrowserContext) {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: 1080 },
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

/** Login as an event player (pk=1081). */
export async function loginEventPlayer(context: BrowserContext) {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: 1081 },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login event player failed: ${resp.status()}`);
  return resp.json();
}
