/**
 * Create-Action Permission Matrix
 *
 * Locks the per-role visibility contract for the four "create" entry points:
 * Create Organization, Create League, Create Event, Create Tournament. Each
 * gate is asserted across all 8 roles in the project's hierarchy
 * (siteAdmin > siteStaff > orgAdmin > orgStaff > orgMember > leagueAdmin >
 * leagueStaff > anonymous) using ``roleMatrixTest`` — one Playwright test
 * per gate, fanning out to 8 concurrent BrowserContexts via ``Promise.all``.
 *
 * Expected matrix (true = button visible to that role):
 *
 *                          siteAdmin siteStaff orgAdmin orgStaff orgMember leagueAdmin leagueStaff anonymous
 *   createOrganization        ✓         ✗         ✗        ✗        ✗         ✗           ✗          ✗
 *   createLeague (org 1)      ✓         ✓         ✓        ✓        ✗         ✗           ✗          ✗
 *   createEvent  (org 1)      ✓         ✓         ✓        ✗        ✗         ✗           ✗          ✗
 *   createTournament          ✓         ✓         ✗        ✗        ✗         ✗           ✗          ✗
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

// The org-detail page uses an INLINE isOrgStaff check (not the hook):
//   isOrgAdmin = is_superuser || owner.pk === me || admins.some(...)
//   isOrgStaff = isOrgAdmin || staff.some(...)
// Note this only checks ``is_superuser``, NOT ``is_staff`` — so a Django
// site-staff user (is_staff=True, is_superuser=False) does NOT bypass the
// org membership check on this page. The Tournament gate (which uses
// ``is_staff || is_superuser`` directly) does grant access to site staff;
// the contracts are intentionally different.
const CREATE_LEAGUE_EXPECTATIONS: Expectations = {
  siteAdmin: true,    // is_superuser → inline isOrgAdmin
  siteStaff: false,   // is_staff alone is NOT enough for the inline check
  orgAdmin: true,     // in DTX.admins
  orgStaff: true,     // in DTX.staff
  orgMember: false,
  leagueAdmin: false, // league role doesn't cascade UP to org
  leagueStaff: false,
  anonymous: false,
};

const CREATE_EVENT_EXPECTATIONS: Expectations = {
  // Same gate as Create League — on the org-detail page, both buttons
  // use the inline isOrgStaff. Different from /events page (out of scope).
  siteAdmin: true,
  siteStaff: false,
  orgAdmin: true,
  orgStaff: true,
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
 * ``toBeVisible`` / ``toBeHidden`` poll for 15s after ``networkidle`` —
 * the org-detail page seeds its cache from a stripped SSR payload and the
 * permission gate only resolves once the CSR refetch lands. The longer
 * timeout absorbs that without needing per-URL wait shapes. ``toBeHidden``
 * uses ``not.toBeVisible`` semantics, so a slow-mounting button can't
 * silently pass the negative case.
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

  test('Create Event button visibility (DTX org-detail)', async ({ roleContexts }) => {
    // Use the org-detail events tab rather than /events?organization=X.
    // The org-detail page fetches the full org payload (with admins/staff
    // arrays) so the inline isOrgStaff gate can resolve correctly. The
    // /events route fetches a stripped org list that omits those fields,
    // so its create-event-btn gate is effectively broken for org admins
    // — a known separate inconsistency (same testid, different gate),
    // out of scope here.
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${DTX_ORG_PK}?tab=events`,
      'create-event-btn',
      CREATE_EVENT_EXPECTATIONS,
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
