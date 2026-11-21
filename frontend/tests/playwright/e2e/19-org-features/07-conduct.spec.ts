import {
  expect,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

const CONDUCT_ROW = /^conduct-row-\d+$/;

test.describe('Org features: conduct @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('member sees the ranking and their own history @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    await expect(page.getByTestId('conduct-tab')).toBeVisible();
    const ranked = data.conduct.ranked_org_user_pks;
    expect(ranked.length).toBeGreaterThan(0);
    for (const pk of ranked) {
      await expect(page.getByTestId(`conduct-row-${pk}`)).toBeVisible();
    }

    // players[0] and member attended every counted event: a shared rank.
    const rankOf = (pk: number) =>
      page.getByTestId(`conduct-row-${pk}`).locator('td').first();
    const tiedRank = (await rankOf(ranked[0]).textContent())?.trim();
    expect(tiedRank).toMatch(/^\d+$/);
    await expect(rankOf(ranked[ranked.length - 1])).toHaveText(tiedRank!);

    await expect(
      page.getByTestId(
        `conduct-row-${data.conduct.new_member_org_user_pk}-value`,
      ),
    ).toHaveText('New');

    const history = page.getByTestId('conduct-history');
    await expect(history).toBeVisible();
    await expect(
      history.getByTestId(`conduct-history-row-${data.events.completed.pk}`),
    ).toBeVisible();
    await page.getByTestId('conduct-rate-explainer').click();
    await expect(
      page.getByTestId('conduct-rate-explainer-content'),
    ).toBeVisible();
  });

  test('outsider sees the members-only note @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'outsider');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    await expect(page.getByTestId('conduct-members-only')).toBeVisible();
    await expect(page.getByTestId(CONDUCT_ROW)).toHaveCount(0);
  });

  test("staff opens another member's history @cicd", async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    const pk = data.conduct.completed_event_member_org_user_pk;
    await page.getByTestId(`conduct-row-${pk}`).click();
    const history = page.getByTestId('conduct-history');
    await expect(history).toBeVisible();
    await expect(
      history.getByTestId(`conduct-history-row-${data.events.completed.pk}`),
    ).toBeVisible();
  });

  test('a private ranking leaves members their own row @cicd', async ({
    page,
    context,
  }) => {
    const orgPk = data.orgs.features.pk;
    await loginOrgFeatures(context, 'admin');
    await orgFeaturesApi(
      context,
      'PATCH',
      `/organizations/${orgPk}/conduct/settings/`,
      { leaderboard_public: false },
    );

    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    await expect(page.getByTestId('conduct-self-only')).toBeVisible();
    const ownPk = data.conduct.ranked_org_user_pks.at(-1)!;
    await expect(page.getByTestId(`conduct-row-${ownPk}`)).toBeVisible();
    await expect(page.getByTestId(CONDUCT_ROW)).toHaveCount(1);
    await expect(page.getByTestId('conduct-history')).toBeVisible();
    await expect(page.getByTestId('conduct-members-only')).toHaveCount(0);
    await expect(page.getByTestId('conduct-members-private')).toHaveCount(0);
    await expect(page.getByTestId('conduct-error')).toHaveCount(0);

    await loginOrgFeatures(context, 'outsider');
    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    await expect(page.getByTestId('org-tab-contributions')).toBeVisible();
    await expect(page.getByTestId('org-tab-conduct')).toHaveCount(0);
    await expect(page).not.toHaveURL(/tab=conduct/);
    await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  test('contributions metric switcher keeps the points total @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=contributions`,
    );

    const total = page.getByTestId('contributions-org-total');
    await expect(total).toContainText('points');
    const before = (await total.textContent()) ?? '';

    const switched = page.waitForResponse(
      (r) =>
        r.url().includes('/standing/contribution/leaderboard/') &&
        r.url().includes('metric=entries'),
    );
    await page.getByTestId('standing-metric-contribution-entries').click();
    expect((await switched).ok()).toBe(true);
    await expect(total).toHaveText(before);
  });

  test('admin edits conduct settings @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'admin');
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=conduct`,
    );
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();

    const halfLife = page.getByTestId('conduct-setting-half_life_days');
    await expect(halfLife).toBeVisible();
    await halfLife.fill('120');
    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/organizations/${pk}/conduct/settings/`),
    );
    await page.getByTestId('org-settings-save').click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);

    await page.reload();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(
      page.getByTestId('conduct-setting-half_life_days'),
    ).toHaveValue('120');

    await page.getByTestId('conduct-settings-enforcement-toggle').click();
    for (const name of [
      'back_of_line_enabled',
      'require_approval_enabled',
      'block_enabled',
    ]) {
      const toggle = page.getByTestId(`conduct-setting-${name}`);
      await expect(toggle).toBeVisible();
      await expect(toggle).not.toBeChecked();
    }
  });
});
