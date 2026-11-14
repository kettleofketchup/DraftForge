import { BASE_URL } from '../../fixtures/base-url';
import {
  expect,
  leaderboardByUser,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: promoter flow @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('promoter sends from the event page, earns a point, staff undoes it @cicd', async ({
    page,
    context,
    browser,
  }) => {
    test.setTimeout(90_000);
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.upcoming.pk;
    const template = data.templates.find((t) => t.org_pk === orgPk && t.name === 'First invite');
    expect(template, 'seeded "First invite" template').toBeDefined();

    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE_URL });
    await loginOrgFeatures(context, 'promoter');
    await visitAndWaitForHydration(page, `/events/${eventPk}`);

    await page.getByTestId('event-promote-btn').click();
    await expect(page).toHaveURL(new RegExp(`tab=promotion.*event=${eventPk}`));
    await expect(page.getByTestId(`promo-event-${eventPk}`)).toHaveAttribute('aria-pressed', 'true');

    const firstSelect = page.locator('[data-testid^="promo-select-"]').first();
    await expect(firstSelect).toBeVisible();
    const selectTestId = await firstSelect.getAttribute('data-testid');
    const recipientPk = Number(selectTestId?.replace('promo-select-', ''));
    expect(recipientPk).toBeGreaterThan(0);
    await firstSelect.click();

    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template!.pk}`).click();
    const message = page.getByTestId('promo-message-text');
    await expect(message).toHaveValue(/^Hey .+ from Features Test Org here\./);
    await expect(page.getByTestId('promo-earn-points-note')).toBeVisible();

    await page.getByTestId('promo-copy-btn').click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toBe(await message.inputValue());

    const sendResponse = page.waitForResponse(
      (r) => r.request().method() === 'POST' && r.url().includes(`/promotion/events/${eventPk}/sends/`),
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    const sendResp = await sendResponse;
    expect(sendResp.status()).toBe(201);
    const send = (await sendResp.json()) as { id: number; points_awarded: number | null };
    expect(send.points_awarded).toBe(1);

    const banner = page.getByTestId('promo-sent-banner');
    await expect(banner).toBeVisible();
    await expect(banner.getByTestId(`promo-undo-${send.id}`)).toBeVisible();
    await expect(page.getByTestId('promo-earned-hint')).toHaveText('You earned 1 points.');
    await expect(page.getByTestId('promo-mark-sent-btn')).toBeDisabled();

    // Org staff stands in as the second sender: this player already has an earning send for the event.
    const staffContext = await browser.newContext({ baseURL: BASE_URL, ignoreHTTPSErrors: true });
    const adminContext = await browser.newContext({ baseURL: BASE_URL, ignoreHTTPSErrors: true });
    try {
      await loginOrgFeatures(staffContext, 'staff');
      const staffPage = await staffContext.newPage();
      const staffCandidates = staffPage.waitForResponse(
        (r) => r.request().method() === 'GET' && r.url().includes(`/events/${eventPk}/candidates/`),
      );
      await visitAndWaitForHydration(staffPage, `/organizations/${orgPk}?tab=promotion&event=${eventPk}`);
      await expect(staffPage.getByTestId(`promo-event-${eventPk}`)).toHaveAttribute('aria-pressed', 'true');
      expect((await staffCandidates).status()).toBe(200);
      await expect(staffPage.getByTestId('promo-candidate-list')).toBeVisible();
      await expect(staffPage.getByText('Loading players...')).toHaveCount(0);
      await expect(staffPage.getByTestId(`promo-candidate-${recipientPk}`)).toHaveCount(0);
      await staffPage.getByTestId('promo-hide-messaged').click();
      await expect(staffPage.getByTestId(`promo-last-messaged-${recipientPk}`)).toBeVisible();
      await staffPage.getByTestId(`promo-select-${recipientPk}`).click();
      await expect(staffPage.getByTestId('promo-no-points-note')).toBeVisible();
      await expect(staffPage.getByTestId('promo-earn-points-note')).toHaveCount(0);

      await loginOrgFeatures(adminContext, 'admin');
      const promoterPk = data.users.promoter.pk;
      const promoterRow = (await leaderboardByUser(adminContext, orgPk)).get(promoterPk);
      expect(promoterRow?.points, 'promoter: 5 (seeded helper) + 1 (promo)').toBe(6);
      const adminPage = await adminContext.newPage();
      await visitAndWaitForHydration(adminPage, `/organizations/${orgPk}?tab=contributions`);
      const adminRow = adminPage.getByTestId(`contributions-row-${promoterRow!.org_user_pk}`);
      await expect(adminRow.locator('td').nth(2)).toHaveText('6');

      const undoResponse = staffPage.waitForResponse(
        (r) => r.request().method() === 'DELETE' && r.url().includes(`/promotion/sends/${send.id}/`),
      );
      await staffPage.getByTestId(`promo-undo-${send.id}`).click();
      expect((await undoResponse).status()).toBe(204);
      await expect(staffPage.getByTestId(`promo-last-messaged-${recipientPk}`)).toHaveCount(0);

      await adminPage.reload();
      await expect(adminRow.locator('td').nth(2)).toHaveText('5');
    } finally {
      await staffContext.close();
      await adminContext.close();
    }
  });
});
