/**
 * Edit + Bracket Permission Matrix
 *
 * Locks the per-role visibility contract for user-edit affordances and
 * the bracket lifecycle (generate / set winner / link Steam match)
 * across every role via ``roleMatrixTest``. The promoter column matches
 * orgMember (Promotion stays locked on AUTH_MATRIX_ORG).
 *
 * Canonical matrix lives in ``docs/dev/auth/roles.md`` — keep that page
 * in sync with the expectations below. Quick reference:
 *
 *                                       siteAdmin siteStaff orgOwner orgAdmin orgStaff orgMember promoter leagueAdmin leagueStaff anonymous
 *   orgUsersTab  (members_private off)  ✓         ✓         ✓        ✓        ✓        ✓         ✓        ✓           ✓           ✗
 *   editUser     (org members tab)      ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✗           ✗           ✗
 *   editUser     (tournament players)   ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✗           ✗           ✗
 *   addPlayer    (tournament players)   ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✓           ✓           ✗
 *   generateBracket                     ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✓           ✓           ✗
 *   setMatchWinner (radiant)            ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✓           ✓           ✗
 *   linkSteamMatch                      ✓         ✓         ✗        ✗        ✗        ✗         ✗        ✗           ✗           ✗
 *   editTournament (detail page)        ✓         ✓         ✓        ✓        ✓        ✗         ✗        ✓           ✓           ✗
 *   deleteTournament (detail page)      ✓         ✓         ✗        ✗        ✗        ✗         ✗        ✗           ✗           ✗
 *
 * One known divergence:
 *
 * - **Link Steam Match** gates on ``useUserStore.isStaff()`` (site
 *   staff only) while the rest of the MatchStatsModal uses
 *   ``useIsLeagueStaff``. Site staff get the button, org/league
 *   admins don't.
 *
 * Documented in ``docs/dev/auth/roles.md``.
 */

import type { Page } from '@playwright/test';
import {
  expect,
  ROLE_NAMES,
  roleMatrixTest as test,
  type RoleName,
} from '../../fixtures';

// Isolated org used by every non-site role in the matrix. Created by
// populate_auth_matrix_data; keeps the gate contract independent of
// any other suite that mutates DTX.
const AUTH_MATRIX_ORG_PK = 8;

// Tournament fixtures from backend/tests/data/tournaments.py. Each
// targets AUTH_MATRIX_LEAGUE (pk=9) so the matrix never touches the
// shared DTX bracket tournaments. pks sit above the auto-incremented
// range used by other populates to keep the explicit-pk creates safe.
//   pk=200 "Auth Matrix No Bracket"        — no bracket → Generate
//   pk=201 "Auth Matrix Pending Bracket"   — pending matches → Set Winner
//   pk=202 "Auth Matrix Completed Bracket" — won matches → Link Steam
const TOURNAMENT_NO_BRACKET_PK = 200;
const TOURNAMENT_PENDING_BRACKET_PK = 201;
const TOURNAMENT_COMPLETED_BRACKET_PK = 202;

type Expectations = Record<RoleName, boolean>;

// Org Users tab → ``organization.can_view_members`` from the backend:
// org members, org staff tier, and staff of the org's leagues. The
// members_private=true case is covered by
// app.tests.test_org_members_privacy (flipping it here would race other roles).
const ORG_USERS_TAB_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: true,
  promoter: true,
  leagueAdmin: true,
  leagueStaff: true,
  anonymous: false,
};

// Edit User on the org members tab → ``useIsOrganizationStaff(currentOrg)``.
// Site admins bypass via the hook's ``is_staff || is_superuser`` short-circuit.
const EDIT_USER_ORG_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  promoter: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// Edit User on the tournament players tab resolves to league scope. The
// save goes through the parent org's OrgUser endpoint (org staff gate), so
// the button follows parent-org staff, not league roles.
const EDIT_USER_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  promoter: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// Generate Bracket → ``useCanEditTournament`` which is an alias for
// ``useIsLeagueStaff(tournament.league, organization)``. Both league
// admins and league staff get the button (league-level operational).
const GENERATE_BRACKET_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true, // owner cascade via useIsOrganizationAdmin → staff
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  promoter: false,
  leagueAdmin: true,
  leagueStaff: true,
  anonymous: false,
};

// Set winner in MatchStatsModal → ``useIsLeagueStaff``. Same cascade
// as Generate Bracket — declaring winners is an operational action.
const SET_WINNER_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  promoter: false,
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
  orgOwner: false, // gate is site-only; owner doesn't cascade here
  orgAdmin: false,
  orgStaff: false,
  orgMember: false,
  promoter: false,
  leagueAdmin: false,
  leagueStaff: false,
  anonymous: false,
};

// Edit Tournament → ``canEditTournament`` mirrors backend ``can_edit_tournament``:
// league admins/staff, or admins/staff of the league's own org.
const EDIT_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: true,
  orgAdmin: true,
  orgStaff: true,
  orgMember: false,
  promoter: false,
  leagueAdmin: true,
  leagueStaff: true,
  anonymous: false,
};

// Delete Tournament stays site staff only.
const DELETE_TOURNAMENT_EXPECTATIONS: Expectations = {
  siteAdmin: true,
  siteStaff: true,
  orgOwner: false,
  orgAdmin: false,
  orgStaff: false,
  orgMember: false,
  promoter: false,
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
    await expect(btn, `${role} should see ${testid}`).toBeVisible({
      timeout: 15000,
    });
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
  await expect(
    matchNode,
    `${role} should see at least one bracket-match-node`,
  ).toBeVisible({
    timeout: 15000,
  });
  await matchNode.click();

  const btn = page.locator(`[data-testid="${testid}"]`).first();
  if (expectVisible) {
    await expect(btn, `${role} should see ${testid}`).toBeVisible({
      timeout: 15000,
    });
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
      assertGate(
        role,
        roleContexts[role].page,
        url,
        testid,
        expectations[role],
      ),
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
      assertModalGate(
        role,
        roleContexts[role].page,
        url,
        testid,
        expectations[role],
      ),
    ),
  );
}

test.describe('Edit + Bracket permission matrix (all roles in parallel)', () => {
  test('Org Users tab visibility', async ({ roleContexts }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${AUTH_MATRIX_ORG_PK}`,
      'org-tab-users',
      ORG_USERS_TAB_EXPECTATIONS,
    );
  });

  test('Edit User button visibility (org members tab)', async ({
    roleContexts,
  }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/organizations/${AUTH_MATRIX_ORG_PK}?tab=users`,
      'edit-user-btn',
      EDIT_USER_ORG_EXPECTATIONS,
    );
  });

  test('Edit User button visibility (tournament players tab)', async ({
    roleContexts,
  }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}/players`,
      'edit-user-btn',
      EDIT_USER_TOURNAMENT_EXPECTATIONS,
    );
  });

  test('Add Player button visibility (tournament players tab)', async ({
    roleContexts,
  }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}/players`,
      'tournamentAddPlayerBtn',
      GENERATE_BRACKET_EXPECTATIONS,
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

  test('Set Match Winner button visibility (radiant)', async ({
    roleContexts,
  }) => {
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

  test('Edit Tournament button visibility (detail page)', async ({
    roleContexts,
  }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}`,
      'tournament-edit-btn',
      EDIT_TOURNAMENT_EXPECTATIONS,
    );
  });

  test('Delete Tournament button visibility (detail page)', async ({
    roleContexts,
  }) => {
    await assertGateAcrossRoles(
      roleContexts,
      `/tournament/${TOURNAMENT_NO_BRACKET_PK}`,
      'tournament-delete-btn',
      DELETE_TOURNAMENT_EXPECTATIONS,
    );
  });
});
