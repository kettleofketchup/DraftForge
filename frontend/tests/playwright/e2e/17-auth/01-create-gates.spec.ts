/**
 * Create-Action Permission Matrix
 *
 * Locks the per-role visibility contract for the create entry points
 * across all 8 roles in the project's hierarchy (siteAdmin > siteStaff >
 * orgAdmin > orgStaff > orgMember > leagueAdmin > leagueStaff >
 * anonymous) using ``roleMatrixTest`` — one Playwright test per gate,
 * fanning out to 8 concurrent BrowserContexts via ``Promise.all``.
 *
 * Expected matrix (✓ = button visible to that role). Two Create Event
 * rows because the org-detail tab and the /events route use different
 * gates (``useIsOrganizationStaff`` vs ``useIsOrganizationAdmin``):
 *
 *                                       siteAdmin siteStaff orgAdmin orgStaff orgMember leagueAdmin leagueStaff anonymous
 *   createOrganization                     ✓         ✗         ✗        ✗        ✗         ✗           ✗          ✗
 *   createLeague    (org-detail)           ✓         ✓         ✓        ✓        ✗         ✗           ✗          ✗
 *   createEvent     (org-detail)           ✓         ✓         ✓        ✓        ✗         ✗           ✗          ✗
 *   createEvent     (/events?org=X)        ✓         ✓         ✓        ✗        ✗         ✗           ✗          ✗
 *   createTournament                       ✓         ✓         ✗        ✗        ✗         ✗           ✗          ✗
 *
 * The site-admin row exists because the permission hooks
 * (``useIsLeagueStaff`` / ``useIsOrganizationAdmin`` etc.) bypass on
 * ``is_staff || is_superuser`` before the entity-null guard — regression
 * locked here so site admins keep edit access on org-/league-less pages.
 *
 * Failure mode: ``Promise.all`` short-circuits on the first rejection, so a
 * single broken role will mask the rest. Re-run after fixing to surface the
 * next failure — acceptable for a contract matrix.
 */

import { roleMatrixTest as test, expect, ROLE_NAMES, type RoleName } from '../../fixtures';
import type { Page } from '@playwright/test';

const DTX_ORG_PK = 1;

type Expectations = Record<RoleName, boolean>;

const CREATE_ORG_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // is_superuser
  siteStaff: false,   // is_staff alone is not enough — route gate is is_superuser only
  orgAdmin: false,
  orgStaff: false,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// The org-detail page now uses ``useIsOrganizationStaff`` from the shared
// permissions hooks (was an inline check that only honoured
// ``is_superuser``). The hook treats ``is_staff || is_superuser`` as a
// site-admin bypass, so a Django site-staff user gains org-staff
// equivalence here.
const CREATE_LEAGUE_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // is_superuser → useIsOrganizationStaff bypass
  siteStaff: true,    // is_staff → same bypass
  orgAdmin: true,     // in DTX.admins
  orgStaff: true,     // in DTX.staff
  orgMember: false,
  leagueAdmin: false, // league role doesn't cascade UP to org
  leagueStaff: false,
  anonymous: false,
};

const CREATE_EVENT_EXPECTATIONS: Expectations = {
  // Same gate as Create League — both use useIsOrganizationStaff via
  // the hook refactor.
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// The /events page uses ``useIsOrganizationAdmin`` against the
// (now full-org) selectedOrg fetched via useOrganization(selectedOrgIdNum).
// The hook's site-admin bypass kicks in for is_staff || is_superuser, so
// site staff also qualify here even without explicit org membership.
const CREATE_EVENT_EVENTS_PAGE_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // is_superuser → useIsOrganizationAdmin bypass
  siteStaff: true,    // is_staff → useIsOrganizationAdmin bypass (post-fix)
  orgAdmin: true,     // in DTX.admins
  orgStaff: false,    // staff is NOT admin (this gate is admin-only)
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

const CREATE_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // gate: is_staff || is_superuser
  siteStaff: true,
  orgAdmin: false,
  orgStaff: false,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

/** Assert a single role's button visibility, named so traces are readable.
 *
 * Positive case polls ``toBeVisible`` for 15s — the org-detail page seeds
 * its query cache from a stripped SSR payload and the permission gate
 * only resolves once the CSR refetch lands the full org. The negative
 * case uses ``not.toBeVisible`` with a 5s ceiling: if the button isn't
 * gated in, it should never appear, so a short wait is enough to catch
 * a slow-but-eventually-visible regression without inflating run time.
 */
async function assertGate(
  role: RoleName,
  page: Page,
  url: string,
  testid: string,
  expectVisible: boolean,
): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState('networkidle');

  const btn = page.locator(`[data-testid="${testid}"]`);
  if (expectVisible) {
    await expect(btn, `${role} should see ${testid}`).toBeVisible({ timeout: 15000 });
  } else {
    await expect(btn, `${role} should NOT see ${testid}`).not.toBeVisible({
      timeout: 5000,
    });
  }
}

/**
 * Fan a gate assertion out to all 8 role contexts concurrently. ``Promise.all``
 * is intentional — for a contract matrix we'd rather know one failure than
 * pay 8× the wall-time. Re-run after fixing to surface the next role.
 */
async function assertGateAcrossRoles(
  roleContexts: Record<RoleName, { page: Page }>,
  url: string,
  testid: string,
  expectations: Expectations,
): Promise<void> {
  await Promise.all(
    ROLE_NAMES.map((role) =>
      assertGate(role, roleContexts[role].page, url, testid, expectations[role]),
    ),
  );
}

test.describe('Create-action permission matrix (8 roles in parallel)', () => {
  test('Create Organization button visibility', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      '/organizations/',
      'create-organization-button',
      CREATE_ORG_EXPECTATIONS,
    );
  });

  test('Create League button visibility (DTX org)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${DTX_ORG_PK}?tab=leagues`,
      'create-league-button',
      CREATE_LEAGUE_EXPECTATIONS,
    );
  });

  test('Create Event button visibility (org-detail events tab)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${DTX_ORG_PK}?tab=events`,
      'create-event-btn',
      CREATE_EVENT_EXPECTATIONS,
    );
  });

  test('Create Event button visibility (/events?organization=X)', async ({ roleContexts }) => {
    // Same testid as the org-detail tab but a different gate (hook-based,
    // admin-only) — see the EVENTS_PAGE expectation comment for the
    // hierarchy difference. This locks the contract for the /events route
    // now that it fetches the full org via useOrganization.
    await assertGateAcrossRoles(
      roleContexts,
      `/events?organization=${DTX_ORG_PK}`,
      'create-event-btn',
      CREATE_EVENT_EVENTS_PAGE_EXPECTATIONS,
    );
  });

  test('Create Tournament button visibility', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      '/tournaments/',
      'tournament-create-button',
      CREATE_TOURNAMENT_EXPECTATIONS,
    );
  });
});
