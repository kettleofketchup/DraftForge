/**
 * Approving a signup in a Deadlock event sets the Deadlock org MMR only.
 *
 * Uses the isolated "Game MMR Org" data (backend tests.data.game_org_mmr).
 * approve-setup rebuilds the event and a pending signup for gom_approve
 * (8007) per test, so reruns start from the same state.
 */

import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import {
  getOrgMembership,
  setupDeadlockApprove,
  type DeadlockApproveSetup,
} from '../../fixtures/game-org-mmr';

const APPROVED_MMR = 2468;

let setup: DeadlockApproveSetup;

async function orgUser(
  context: import('@playwright/test').BrowserContext,
  userPk: number,
  orgPk: number,
) {
  const dump = await getOrgMembership(context, userPk);
  const entry = dump.org_users.find((ou) => ou.organization_pk === orgPk);
  expect(
    entry,
    'approve user must be a member of the Game MMR Org',
  ).toBeTruthy();
  return entry!;
}

test.describe('Deadlock org MMR approval (@cicd)', () => {
  test.beforeEach(async ({ context, loginAdmin }) => {
    setup = await setupDeadlockApprove(context);
    await loginAdmin();
  });

  test('approving in a Deadlock event writes the Deadlock org MMR', async ({
    context,
    page,
  }) => {
    const before = await orgUser(context, setup.user_pk, setup.org_pk);
    expect(before.game_mmrs['1']).toBe(setup.dota_mmr);
    expect(before.game_mmrs['2'] ?? 0).toBe(0);

    await visitAndWaitForHydration(page, `/events/${setup.event_pk}`);
    await page.getByTestId('event-tab-signups').click();
    const approve = page.getByTestId(`approve-signup-${setup.signup_pk}`);
    await expect(approve).toBeVisible({ timeout: 10000 });
    await approve.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    await expect(dialog.getByTestId('mmr-modal-game-title')).toContainText(
      'Deadlock',
    );
    await expect(
      dialog.getByTestId('rank-signals-deadlock-rank-value'),
    ).toHaveText('Phantom 4 (e2e)');
    const input = dialog.getByTestId('mmr-input');
    await expect(input).toHaveValue('');
    await input.fill(String(APPROVED_MMR));
    await dialog.getByTestId('mmr-modal-approve').click();

    const confirmBox = page.locator('[role="alertdialog"]');
    await expect(confirmBox).toBeVisible({ timeout: 5000 });
    await confirmBox.getByTestId('mmr-confirm-approve').click();
    await expect(dialog).not.toBeVisible({ timeout: 10000 });
    await expect(approve).toHaveCount(0, { timeout: 10000 });

    const after = await orgUser(context, setup.user_pk, setup.org_pk);
    expect(after.game_mmrs['2']).toBe(APPROVED_MMR);
    expect(after.game_mmrs['1']).toBe(setup.dota_mmr);
    expect(after.mmr).toBe(setup.dota_mmr);
  });
});
