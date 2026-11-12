import type { Browser } from '@playwright/test';

import { API_URL } from '../fixtures/base-url';
import { getEventsTestData } from '../fixtures/events';
import { getTournamentByKey } from './tournament';

/** Routes swept by the page-wide audits (overflow, hydration, layout). */
export type AuditRoute = { path: string };

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
      { path: '/' },
      { path: '/events' },
      { path: `/events/${events.pk}` },
      { path: '/tournaments' },
      { path: `/tournament/${tournament.pk}/players` },
      { path: `/organizations/${events.orgPk}` },
      { path: '/leagues' },
      { path: '/user/1003' },
      { path: '/leagues/1' },
      { path: `/tournament/${tournament.pk}/bracket` },
      { path: `/events/${events.pk}/discord` },
      { path: `/event-series/${series.id}` },
    ];
    if (routes.length !== AUDIT_ROUTE_COUNT) {
      throw new Error(`AUDIT_ROUTE_COUNT is ${AUDIT_ROUTE_COUNT} but ${routes.length} routes resolved`);
    }
    return routes;
  } finally {
    await ctx.close();
  }
}
