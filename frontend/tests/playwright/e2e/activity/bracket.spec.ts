/**
 * Discord Activity bracket view.
 *
 * The Activity runs inside a same-origin harness iframe that answers the
 * embedded-app-sdk protocol; the backend's TEST-stack Discord fake verifies
 * the session. The Activity opens on the user's hero draft, then the header
 * menu switches to the bracket, which must fill the frame (it once collapsed
 * to 2px inside the root ScrollArea) and render its match nodes.
 */

import {
  expect,
  harnessCommands,
  openActivityHarness,
  setupDiscordActivity,
  test,
} from '../../fixtures';

test.describe('@cicd Discord Activity bracket', () => {
  test('@cicd the bracket fills the Activity and shows its matches', async ({
    context,
    page,
  }) => {
    const setup = await setupDiscordActivity(context);
    const activity = await openActivityHarness(page, setup);

    await expect(activity.getByTestId('activity-header')).toBeVisible({
      timeout: 30_000,
    });
    await expect(activity.getByTestId('activity-menu-trigger')).toBeVisible();

    const commands = (await harnessCommands(page)).map((c) => c.cmd);
    expect(commands).toContain('AUTHORIZE');
    expect(commands).toContain('AUTHENTICATE');

    await activity.getByTestId('activity-menu-trigger').click();
    await activity.getByTestId('activity-menu-bracket').click();
    // The setup user captains this hero draft, so leaving it asks first.
    await expect(activity.getByTestId('activity-leave-dialog')).toBeVisible();
    await activity.getByTestId('activity-leave-confirm').click();

    const bracket = activity.getByTestId('bracketContainer');
    await expect(bracket).toBeVisible();
    await expect
      .poll(async () => (await bracket.boundingBox())?.height ?? 0)
      .toBeGreaterThan(200);
    await expect(bracket.getByTestId('bracket-match-node')).toHaveCount(6);
    await expect(
      bracket.getByTestId('bracket-match-node').first(),
    ).toBeInViewport();
  });
});
