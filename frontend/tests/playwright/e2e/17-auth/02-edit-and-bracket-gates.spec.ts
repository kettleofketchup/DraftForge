/**
 * Edit + Bracket Permission Matrix
 *
 * Locks the per-role visibility contract for user-edit affordances and
 * the bracket lifecycle (generate / set winner / link Steam match)
 * across the 8 roles via ``roleMatrixTest``.
 *
 * Canonical matrix lives in ``docs/dev/auth/roles.md`` — keep that page
 * in sync with the expectations below. Quick reference:
 *
 *                                       siteAdmin siteStaff orgAdmin orgStaff orgMember leagueAdmin leagueStaff anonymous
 *   editUser     (org members tab)        ✓         ✓         ✓        ✓        ✗         ✗           ✗          ✗
 *   editUser     (tournament players)     ✓         ✓         ✗        ✗        ✗         ✓           ✗          ✗
 *   generateBracket                       ✓         ✓         ✓        ✓        ✗         ✓           ✓          ✗
 *   setMatchWinner (radiant)              ✓         ✓         ✓        ✓        ✗         ✓           ✓          ✗
 *   linkSteamMatch                        ✓         ✓         ✗        ✗        ✗         ✗           ✗          ✗
 *
 * Two known divergences:
 *
 * - **Tournament players edit** uses ``useIsLeagueAdmin`` (via the
 *   hasErrors panel's ``deriveEditScope`` returning league scope) while
 *   the org members tab uses ``useIsOrganizationStaff``. Same user
 *   record, two gates — org staff can edit a user from the org page
 *   but not from a tournament players page with profile errors.
 *
 * - **Link Steam Match** gates on ``useUserStore.isStaff()`` (site
 *   staff only) while the rest of the MatchStatsModal uses
 *   ``useIsLeagueStaff``. Site staff get the button, org/league
 *   admins don't.
 *
 * Both are documented in ``docs/dev/auth/roles.md``.
 */

import { roleMatrixTest as test, expect, ROLE_NAMES, type RoleName } from '../../fixtures';
import type { Page } from '@playwright/test';

const DTX_ORG_PK = 1;

// Tournament fixtures from backend/tests/data/tournaments.py. Picked
// for their bracket state so each gate has a page where the affordance
// would naturally appear:
//   pk=4 "Draft Test"            — DTX League, no bracket → Generate
//   pk=3 "Pending Bracket Test"  — DTX League, matches w/ no winners → Set Winner
//   pk=1 "Completed Bracket Test"— DTX League, matches w/ winners → Link Steam
const TOURNAMENT_NO_BRACKET_PK = 4;
const TOURNAMENT_PENDING_BRACKET_PK = 3;
const TOURNAMENT_COMPLETED_BRACKET_PK = 1;

type Expectations = Record<RoleName, boolean>;

// Edit User on the org members tab → ``useIsOrganizationStaff(currentOrg)``.
// Site admins bypass via the hook's ``is_staff || is_superuser`` short-circuit.
const EDIT_USER_ORG_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// Edit User on the tournament players tab — first match on the page is
// the hasErrors panel which uses ``deriveEditScope({ league, currentOrg })``.
// That returns ``{ kind: 'league', league }`` (no ``.organization`` on
// the scope) when the tournament has a league, so the gate is
// ``useIsLeagueAdmin(league, undefined)``. The fallback to
// ``league.organization`` for the org-admin cascade only triggers when
// the leagueStore has the parent org embedded — in this navigation
// path it doesn't, so org admins miss the cascade. siteAdmin/siteStaff
// pass via the hook's site-admin bypass; leagueAdmin via direct
// membership in League.admins. Documented in roles.md as a known
// divergence from the org members tab gate.
const EDIT_USER_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: false,   // org-admin cascade doesn't trigger (no embedded org)
  orgStaff: false,
  orgMember: false,
  leagueAdmin: true,
  leagueStaff: false,
  anonymous: false,
};

// Generate Bracket → ``useCanEditTournament`` which is an alias for
// ``useIsLeagueStaff(tournament.league, organization)``. Both league
// admins and league staff get the button (league-level operational).
const GENERATE_BRACKET_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: true,
  leagueStaff: true,
  anonymous: false,
};

// Set winner in MatchStatsModal → ``useIsLeagueStaff``. Same cascade
// as Generate Bracket — declaring winners is an operational action.
const SET_WINNER_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  leagueAdmin: true,
  leagueStaff: true,
  anonymous: false,
};

// Link Steam Match button gates on the ``isStaff`` selector from
// useUserStore, which only honours Django ``is_staff || is_superuser``
// — it does NOT cascade through org/league admins like the rest of the
// modal. Tracked as a known divergence in roles.md.
const LINK_STEAM_MATCH_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgAdmin: false,
  orgStaff: false,
  orgMember: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

/** Assert a single role's button visibility, named so traces are readable. */
async function assertGate(
  role: RoleName,
  page: Page,
  url: string,
  testid: string,
  expectVisible: boolean,
): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState('networkidle');

  const btn = page.locator(`[data-testid="${testid}"]`).first();
  if (expectVisible) {
    await expect(btn, `${role} should see ${testid}`).toBeVisible({ timeout: 15000 });
  } else {
    await expect(btn, `${role} should NOT see ${testid}`).not.toBeVisible({
      timeout: 5000,
    });
  }
}

/**
 * Assert a button inside the bracket MatchStatsModal — caller still
 * provides the destination URL (so we can target different tournaments
 * with different match states). Opens the modal by clicking the first
 * bracket match node; the modal renders unconditionally on click, so
 * the gate is only on the button inside it.
 */
async function assertModalGate(
  role: RoleName,
  page: Page,
  url: string,
  testid: string,
  expectVisible: boolean,
): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState('networkidle');

  // Wait for the bracket to render before clicking. Anonymous users
  // still see the tournament page; if no match nodes exist for them
  // the test will surface that as a failure, which is the right
  // signal.
  const matchNode = page.locator('[data-testid="bracket-match-node"]').first();
  await expect(matchNode, `${role} should see at least one bracket-match-node`).toBeVisible({
    timeout: 15000,
  });
  await matchNode.click();

  const btn = page.locator(`[data-testid="${testid}"]`).first();
  if (expectVisible) {
    await expect(btn, `${role} should see ${testid}`).toBeVisible({ timeout: 15000 });
  } else {
    await expect(btn, `${role} should NOT see ${testid}`).not.toBeVisible({
      timeout: 5000,
    });
  }
}

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

async function assertModalGateAcrossRoles(
  roleContexts: Record<RoleName, { page: Page }>,
  url: string,
  testid: string,
  expectations: Expectations,
): Promise<void> {
  await Promise.all(
    ROLE_NAMES.map((role) =>
      assertModalGate(role, roleContexts[role].page, url, testid, expectations[role]),
    ),
  );
}

test.describe('Edit + Bracket permission matrix (8 roles in parallel)', () => {
  test('Edit User button visibility (org members tab)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${DTX_ORG_PK}?tab=users`,
      'edit-user-btn',
      EDIT_USER_ORG_EXPECTATIONS,
    );
  });

  test('Edit User button visibility (tournament players tab)', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}/players`,
      'edit-user-btn',
      EDIT_USER_TOURNAMENT_EXPECTATIONS,
    );
  });

  test('Generate Bracket button visibility', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}/bracket`,
      'generateBracketButton',
      GENERATE_BRACKET_EXPECTATIONS,
    );
  });

  test('Set Match Winner button visibility (radiant)', async ({ roleContexts }) => {
    // Anonymous can't open the modal in a meaningful way (the bracket
    // is read-only for them and the match node still renders), so the
    // "see no button" branch fires after the modal opens with the
    // button absent.
    await assertModalGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_PENDING_BRACKET_PK}/bracket`,
      'radiantWinsButton',
      SET_WINNER_EXPECTATIONS,
    );
  });

  test('Link Steam Match button visibility', async ({ roleContexts }) => {
    await assertModalGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_COMPLETED_BRACKET_PK}/bracket`,
      'link-steam-match-btn',
      LINK_STEAM_MATCH_EXPECTATIONS,
    );
  });
});
