/**
 * Tests for Organization-Scoped MMR System
 *
 * Verifies that when a user is added to a tournament:
 * 1. An OrgUser record is created for the tournament's organization
 * 2. A LeagueUser record is created for the tournament's league
 */

import { expect, test } from '../../fixtures';
import { BASE_URL } from '../../fixtures/constants';

// API helper to get user's org membership data
async function getUserOrgMembership(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  userPk: number
): Promise<{
  user: { pk: number; username: string; discordId: string };
  org_users: Array<{
    pk: number;
    organization_pk: number;
    organization_name: string;
    mmr: number;
  }>;
  league_users: Array<{
    pk: number;
    league_pk: number;
    league_name: string;
    org_user_pk: number;
    mmr: number;
  }>;
} | null> {
  const response = await context.request.get(
    `${BASE_URL}/api/tests/user/${userPk}/org-membership/`
  );
  if (!response.ok()) return null;
  return (await response.json()) as {
    user: { pk: number; username: string; discordId: string };
    org_users: Array<{
      pk: number;
      organization_pk: number;
      organization_name: string;
      mmr: number;
    }>;
    league_users: Array<{
      pk: number;
      league_pk: number;
      league_name: string;
      org_user_pk: number;
      mmr: number;
    }>;
  };
}

// API helper to get tournament data
async function getTournament(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  tournamentPk: number
): Promise<{
  pk: number;
  name: string;
  league: { pk: number; name: string; organizations: Array<{ pk: number; name: string }> } | null;
  users: Array<{ pk: number; username: string }>;
} | null> {
  const response = await context.request.get(
    `${BASE_URL}/api/tournament/${tournamentPk}/`
  );
  if (!response.ok()) return null;
  return (await response.json()) as {
    pk: number;
    name: string;
    league: { pk: number; name: string; organizations: Array<{ pk: number; name: string }> } | null;
    users: Array<{ pk: number; username: string }>;
  };
}

// API helper to find a user not in tournament
async function findUserNotInTournament(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  tournamentUserPks: number[]
): Promise<{ pk: number; username: string } | null> {
  // Get all users
  const response = await context.request.get(`${BASE_URL}/api/users/`);
  if (!response.ok()) return null;

  const users = (await response.json()) as Array<{ pk: number; username: string }>;

  // Find a user not in the tournament
  const userNotInTournament = users.find(
    (u) => !tournamentUserPks.includes(u.pk) && u.username
  );

  return userNotInTournament || null;
}

test.describe('Organization-Scoped MMR - Tournament User Membership', () => {
  test('adding user to tournament creates OrgUser and LeagueUser records', async ({
    page,
    context,
    loginAdmin,
  }) => {
    // Login as admin
    await loginAdmin();

    // Get a tournament with a league (use tournament 1 which should have DTX league)
    const tournament = await getTournament(context, 1);
    expect(tournament).not.toBeNull();
    expect(tournament!.league).not.toBeNull();

    const league = tournament!.league!;
    const org = league.organizations[0];
    expect(org).toBeDefined();

    // Find a user not in this tournament
    const tournamentUserPks = tournament!.users.map((u) => u.pk);
    const userToAdd = await findUserNotInTournament(context, tournamentUserPks);
    expect(userToAdd).not.toBeNull();

    // Check user's current org membership (may or may not exist)
    const membershipBefore = await getUserOrgMembership(context, userToAdd!.pk);
    const hadOrgUserBefore = membershipBefore?.org_users.some(
      (ou) => ou.organization_pk === org.pk
    );
    const hadLeagueUserBefore = membershipBefore?.league_users.some(
      (lu) => lu.league_pk === league.pk
    );

    // Navigate to tournament page
    await page.goto(`${BASE_URL}/tournament/${tournament!.pk}`);
    await page.waitForLoadState('networkidle');

    // Click Players tab if not already on it
    const playersTab = page.locator('[data-testid="players-tab"]');
    if (await playersTab.isVisible()) {
      await playersTab.click();
    }

    // Click Add Player button
    const addPlayerBtn = page.locator('[data-testid="tournamentAddPlayerBtn"]');
    await expect(addPlayerBtn).toBeVisible({ timeout: 10000 });
    await addPlayerBtn.click();

    // Wait for modal and search input
    const searchInput = page.locator('[data-testid="playerSearchInput"]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Search for the user
    await searchInput.fill(userToAdd!.username);
    await page.waitForTimeout(500); // Wait for search results

    // Click on the user option
    const playerOption = page.locator(
      `[data-testid="playerOption-${userToAdd!.username}"]`
    );
    await expect(playerOption).toBeVisible({ timeout: 5000 });
    await playerOption.click();

    // Wait for success (user card should appear)
    const userCard = page.locator(
      `[data-testid="usercard-${userToAdd!.username}"]`
    );
    await expect(userCard).toBeVisible({ timeout: 10000 });

    // Verify OrgUser and LeagueUser records were created
    const membershipAfter = await getUserOrgMembership(context, userToAdd!.pk);
    expect(membershipAfter).not.toBeNull();

    // Check OrgUser exists for the tournament's organization
    const orgUser = membershipAfter!.org_users.find(
      (ou) => ou.organization_pk === org.pk
    );
    expect(orgUser).toBeDefined();
    expect(orgUser!.organization_name).toBe(org.name);

    // Check LeagueUser exists for the tournament's league
    const leagueUser = membershipAfter!.league_users.find(
      (lu) => lu.league_pk === league.pk
    );
    expect(leagueUser).toBeDefined();
    expect(leagueUser!.league_name).toBe(league.name);
    expect(leagueUser!.org_user_pk).toBe(orgUser!.pk);

    // Log results for debugging
    console.log(
      `User ${userToAdd!.username} (pk=${userToAdd!.pk}) added to tournament ${tournament!.name}`
    );
    console.log(
      `  OrgUser: ${hadOrgUserBefore ? 'existed' : 'created'} for ${org.name}`
    );
    console.log(
      `  LeagueUser: ${hadLeagueUserBefore ? 'existed' : 'created'} for ${league.name}`
    );
  });

  test('tournament users API returns mmr from OrgUser', async ({
    context,
    loginAdmin,
  }) => {
    // Login as admin
    await loginAdmin();

    // Get a tournament with users
    const tournament = await getTournament(context, 1);
    expect(tournament).not.toBeNull();
    expect(tournament!.users.length).toBeGreaterThan(0);

    // Get the first user's data from the tournament response
    const tournamentUser = tournament!.users[0] as {
      pk: number;
      username: string;
      mmr?: number;
    };

    // The mmr in the tournament response should come from OrgUser
    // (This is handled by OrgUserSerializer in the backend)
    if (tournament!.league) {
      const membership = await getUserOrgMembership(context, tournamentUser.pk);
      expect(membership).not.toBeNull();

      const orgUser = membership!.org_users.find(
        (ou) => ou.organization_pk === tournament!.league!.organizations[0]?.pk
      );

      // If user has an OrgUser record, verify mmr matches
      if (orgUser && tournamentUser.mmr !== undefined) {
        expect(tournamentUser.mmr).toBe(orgUser.mmr);
      }
    }
  });
});
