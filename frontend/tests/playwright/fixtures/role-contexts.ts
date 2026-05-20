/**
 * Role-Contexts Fixture
 *
 * Provides a map of pre-authenticated BrowserContext + Page pairs, one per
 * role in the project's permission hierarchy. The canonical role list and
 * gate matrix lives in ``docs/dev/auth/roles.md`` — keep this fixture in
 * sync with that document whenever a role is added, renamed, or removed.
 *
 * Designed for "matrix" tests that assert UI gates by fanning out across
 * roles with ``Promise.all``:
 *
 *   test('Create X gate (all roles)', async ({ roleContexts }) => {
 *     await Promise.all(
 *       Object.entries(roleContexts).map(async ([role, { page }]) => {
 *         await page.goto('/x');
 *         const btn = page.locator('[data-testid="create-x"]');
 *         EXPECTATIONS[role] ? await expect(btn).toBeVisible()
 *                            : await expect(btn).toBeHidden();
 *       }),
 *     );
 *   });
 *
 * Eight roles in the hierarchy (site admin > org admin/staff > league
 * admin/staff > org member > anonymous):
 *
 *   - siteAdmin     — is_superuser=True, is_staff=True (kettleofketchup)
 *   - siteStaff     — is_staff=True, is_superuser=False (hurk_)
 *   - orgAdmin      — Organization.admins of AUTH_MATRIX_ORG (pk=1090)
 *   - orgStaff      — Organization.staff of AUTH_MATRIX_ORG (pk=1091)
 *   - orgMember     — OrgUser of AUTH_MATRIX_ORG, no role (pk=1092)
 *   - leagueAdmin   — League.admins of AUTH_MATRIX_LEAGUE (pk=1093)
 *   - leagueStaff   — League.staff of AUTH_MATRIX_LEAGUE (pk=1094)
 *   - anonymous     — fresh context, no login
 *
 * The non-site roles target the isolated AUTH_MATRIX_ORG (pk=8) and
 * AUTH_MATRIX_LEAGUE (pk=9) — not DTX. This keeps the matrix from
 * flapping when other suites mutate DTX memberships, and vice versa.
 *
 * All 8 contexts are created and authenticated concurrently in the fixture
 * setup; the test body then drives them in parallel as well. With Promise.all
 * the first failure short-circuits the rest — acceptable for "is the gate
 * correct" matrix checks; use per-test parallelism when you need
 * independent failure boundaries.
 */

import {
  test as base,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import {
  loginAdmin,
  loginStaff,
  loginAuthMatrixOrgAdmin,
  loginAuthMatrixOrgStaff,
  loginAuthMatrixOrgMember,
  loginAuthMatrixLeagueAdmin,
  loginAuthMatrixLeagueStaff,
} from './auth';

export type RoleName =
  | 'siteAdmin'
  | 'siteStaff'
  | 'orgAdmin'
  | 'orgStaff'
  | 'orgMember'
  | 'leagueAdmin'
  | 'leagueStaff'
  | 'anonymous';

export interface RoleSession {
  context: BrowserContext;
  page: Page;
}

export type RoleContexts = Record<RoleName, RoleSession>;

/**
 * Stable ordered list of roles for tests that want to iterate
 * deterministically. The order also matches the rendered "permission
 * hierarchy" — site admin first, anonymous last.
 */
export const ROLE_NAMES: readonly RoleName[] = [
  'siteAdmin',
  'siteStaff',
  'orgAdmin',
  'orgStaff',
  'orgMember',
  'leagueAdmin',
  'leagueStaff',
  'anonymous',
] as const;

type RoleLogin = (context: BrowserContext) => Promise<void>;

/**
 * Maps each role to the login fixture that authenticates a fresh
 * BrowserContext for that role. Anonymous resolves immediately — no login.
 */
// All non-site roles target AUTH_MATRIX_ORG (pk=8) / AUTH_MATRIX_LEAGUE
// (pk=9), not DTX. That keeps the matrix isolated from every other
// suite — anyone mutating DTX admins/staff can't flap our contract,
// and vice versa.
const ROLE_LOGINS: Record<RoleName, RoleLogin> = {
  siteAdmin: loginAdmin,
  siteStaff: loginStaff,
  orgAdmin: loginAuthMatrixOrgAdmin,
  orgStaff: loginAuthMatrixOrgStaff,
  orgMember: loginAuthMatrixOrgMember,
  leagueAdmin: loginAuthMatrixLeagueAdmin,
  leagueStaff: loginAuthMatrixLeagueStaff,
  anonymous: async () => {
    /* no login */
  },
};

/**
 * Build a RoleContexts object by creating 8 independent BrowserContexts
 * and logging each in concurrently. If any role's login fails, every
 * already-created context is closed before re-throwing — without the
 * cleanup the fixture's teardown never runs (it's tied to ``use()``)
 * and orphaned contexts leak across tests.
 */
export async function setupRoleContexts(browser: Browser): Promise<RoleContexts> {
  const createdContexts: BrowserContext[] = [];
  try {
    const entries = await Promise.all(
      ROLE_NAMES.map(async (role): Promise<[RoleName, RoleSession]> => {
        const context = await browser.newContext({ ignoreHTTPSErrors: true });
        createdContexts.push(context);
        await ROLE_LOGINS[role](context);
        const page = await context.newPage();
        return [role, { context, page }];
      }),
    );
    return Object.fromEntries(entries) as RoleContexts;
  } catch (err) {
    // ``Promise.all`` rejects on the first failure but the other login
    // promises keep running and may also push contexts onto the list.
    // Wait for the in-flight settles and close everything we made.
    await Promise.allSettled(
      createdContexts.map((c) => c.close().catch(() => {})),
    );
    throw err;
  }
}

/**
 * Extended test fixture with ``roleContexts`` available alongside the
 * standard fixtures. Tests that need the matrix import this ``test``
 * instead of the default auth ``test``.
 */
export const test = base.extend<{ roleContexts: RoleContexts }>({
  roleContexts: async ({ browser }, use) => {
    const roleContexts = await setupRoleContexts(browser);
    await use(roleContexts);
    await Promise.all(
      Object.values(roleContexts).map(({ context }) => context.close()),
    );
  },
});

export { expect } from '@playwright/test';
