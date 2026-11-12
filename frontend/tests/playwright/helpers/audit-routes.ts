import type { Browser } from '@playwright/test';

import { API_URL } from '../fixtures/base-url';
import { getEventsTestData } from '../fixtures/events';
import { getTournamentByKey } from './tournament';

/**
 * Routes swept by the page-wide audits (overflow, hydration, layout). `name` is the route
 * pattern: stable across reseeds, unlike `path`, which carries database ids.
 */
export type AuditRoute = { name: string; path: string };

// Tests are generated before the routes resolve, so the count is fixed up front.
// resolveAuditRoutes throws if it drifts.
export const AUDIT_ROUTE_COUNT = 12;

export async function resolveAuditRoutes(browser: Browser): Promise<AuditRoute[]> {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    const tournament = await getTournamentByKey(ctx, 'completed_bracket');
    if (!tournament) {
      throw new Error("Tournament 'completed_bracket' not found. Run `just db::populate::all`.");
    }
    const events = await getEventsTestData(ctx);
    // No fixture exposes a repeater id, and "Weekly Inhouse" has no pinned pk.
    const repResp = await ctx.request.get(`${API_URL}/events/repeaters/?organization=${events.orgPk}`);
    const repeaters = await repResp.json();
    const series = repeaters.find((r: { name: string }) => r.name === 'Weekly Inhouse');
    if (!series) {
      throw new Error("Repeater 'Weekly Inhouse' not found. Run `just db::populate::all`.");
    }
    const routes: AuditRoute[] = [
      { name: '/', path: '/' },
      { name: '/events', path: '/events' },
      { name: '/events/:eventId', path: `/events/${events.pk}` },
      { name: '/tournaments', path: '/tournaments' },
      { name: '/tournament/:pk/players', path: `/tournament/${tournament.pk}/players` },
      { name: '/organizations/:organizationId', path: `/organizations/${events.orgPk}` },
      { name: '/leagues', path: '/leagues' },
      { name: '/user/:pk', path: '/user/1003' },
      { name: '/leagues/:leagueId', path: '/leagues/1' },
      { name: '/tournament/:pk/bracket', path: `/tournament/${tournament.pk}/bracket` },
      { name: '/events/:eventId/discord', path: `/events/${events.pk}/discord` },
      { name: '/event-series/:repeaterId', path: `/event-series/${series.id}` },
    ];
    if (routes.length !== AUDIT_ROUTE_COUNT) {
      throw new Error(`AUDIT_ROUTE_COUNT is ${AUDIT_ROUTE_COUNT} but ${routes.length} routes resolved`);
    }
    return routes;
  } finally {
    await ctx.close();
  }
}
