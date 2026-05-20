/**
 * Create-Action Permission Matrix
 *
 * Locks the per-role visibility contract for the create entry points
 * across all 8 roles in the project's hierarchy (siteAdmin > siteStaff >
 * orgAdmin > orgStaff > orgMember > leagueAdmin > leagueStaff >
 * anonymous) using ``roleMatrixTest`` — one Playwright test per gate,
 * fanning out to 8 concurrent BrowserContexts via ``Promise.all``.
 *
 * The canonical matrix and its rationale live in
 * ``docs/dev/auth/roles.md``. The diagram below is a quick reference;
 * if it drifts from that page, the doc is authoritative.
 *
 * Expected matrix (✓ = button visible to that role). The Create Event
 * row is locked separately for the org-detail tab and the /events
 * route — they share the same testid and now share the same gate
 * (``useIsOrganizationStaff``), but the matrix asserts both to lock
 * the contract end-to-end. The orgOwner column should match orgAdmin
 * everywhere — owner is admin by the permission cascade:
 *
 *                                       siteAdmin siteStaff orgOwner orgAdmin orgStaff orgMember leagueAdmin leagueStaff anonymous
 *   createOrganization                     ✓         ✓         ✓        ✓        ✓        ✓         ✓           ✓          ✗
 *   createLeague    (org-detail)           ✓         ✓         ✓        ✓        ✓        ✗         ✗           ✗          ✗
 *   createEvent     (org-detail)           ✓         ✓         ✓        ✓        ✓        ✗         ✗           ✗          ✗
 *   createEvent     (/events?org=X)        ✓         ✓         ✓        ✓        ✓        ✗         ✗           ✗          ✗
 *   createTournament                       ✓         ✓         ✓        ✓        ✗        ✗         ✓           ✗          ✗
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

// Isolated org used by every non-site role in the matrix. Created by
// populate_auth_matrix_data; keeps the gate contract independent of
// any other suite that mutates DTX.
const AUTH_MATRIX_ORG_PK = 8;

type Expectations = Record<RoleName, boolean>;

// Any logged-in user can create their own organization (the backend
// OrganizationView.create permission has always been ``IsAuthenticated``;
// the frontend gate was over-restrictive). Only anonymous is gated out.
const CREATE_ORG_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: true,
  leagueAdmin: true,
  leagueStaff: true,
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
  orgOwner: true,     // owner-implies-admin cascade in useIsOrganizationAdmin
  orgAdmin: true,     // in AUTH_MATRIX_ORG.admins
  orgStaff: true,     // in AUTH_MATRIX_ORG.staff
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
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// /events now uses ``useIsOrganizationStaff`` against the full org
// fetched via useOrganization(selectedOrgIdNum). Same gate as the
// org-detail Events tab — events are operational, not governance,
// so staff get the create button. Site admin bypass still applies via
// the hook's is_staff || is_superuser short-circuit.
const CREATE_EVENT_EVENTS_PAGE_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// Tournament gate mirrors the backend's ``has_league_admin_access``
// cascade via ``useCanCreateAnyTournament``: site admin OR admin of any
// org (admin_organization_ids non-empty) OR admin of any league
// (admin_league_ids non-empty). Staff roles can't create tournaments —
// only admins can, matching the backend perform_create check.
const CREATE_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // is_superuser
  siteStaff: true,    // is_staff bypass (matches frontend convention)
  orgOwner: true,     // owner pk merged into admin_organization_ids
  orgAdmin: true,     // admin_organization_ids: [8]
  orgStaff: false,    // staff doesn't cascade to admin
  orgMember: false,
  leagueAdmin: true,  // admin_league_ids: [9]
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

  test('Create League button visibility (auth-matrix org)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${AUTH_MATRIX_ORG_PK}?tab=leagues`,
      'create-league-button',
      CREATE_LEAGUE_EXPECTATIONS,
    );
  });

  test('Create Event button visibility (org-detail events tab)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${AUTH_MATRIX_ORG_PK}?tab=events`,
      'create-event-btn',
      CREATE_EVENT_EXPECTATIONS,
    );
  });

  test('Create Event button visibility (/events?organization=X)', async ({ roleContexts }) => {
    // Same testid and same gate as the org-detail tab — both use
    // ``useIsOrganizationStaff`` now. The /events route fetches the
    // full org via useOrganization(selectedOrgIdNum) so the staff/admin
    // arrays are populated; this test locks the route-level contract
    // explicitly so a future regression to the stripped-payload path
    // shows up here.
    await assertGateAcrossRoles(
      roleContexts,
      `/events?organization=${AUTH_MATRIX_ORG_PK}`,
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
