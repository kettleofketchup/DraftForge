/**
 * Creating a league on the org page adds its card and bumps the tab count without a reload.
 */

import {
  expect,
  loginAdmin,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { getCsrfToken } from '../../fixtures/events';

test('new league appears on an org page that already has one @cicd', async ({
  context,
  page,
}) => {
  await loginAdmin(context);
  const stamp = Date.now();
  const firstName = `First League ${stamp}`;
  const secondName = `Second League ${stamp}`;

  const orgResp = await postWithCsrf(context, '/api/organizations/', {
    name: `League List Org ${stamp}`,
  });
  expect(orgResp.status(), await orgResp.text()).toBe(201);
  const orgPk = (await orgResp.json()).pk as number;
  const leaguePks: number[] = [];

  try {
    const firstResp = await postWithCsrf(context, '/api/leagues/', {
      name: firstName,
      organization_id: orgPk,
    });
    expect(firstResp.status(), await firstResp.text()).toBe(201);
    leaguePks.push((await firstResp.json()).pk);

    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.getByText(firstName)).toBeVisible();
    await expect(page.getByTestId('org-tab-leagues')).toHaveText('Leagues (1)');

    let reloaded = false;
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame()) reloaded = true;
    });

    await page.getByTestId('create-league-button').click();
    await page.getByPlaceholder('League name').fill(secondName);
    const created = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/leagues/') && r.request().method() === 'POST',
    );
    await page.getByTestId('form-dialog-submit').click();
    leaguePks.push((await (await created).json()).pk);

    await expect(page.getByText(secondName)).toBeVisible();
    await expect(page.getByTestId('org-tab-leagues')).toHaveText('Leagues (2)');
    expect(reloaded).toBe(false);
  } finally {
    const headers = { 'X-CSRFToken': await getCsrfToken(context) };
    for (const pk of leaguePks) {
      await context.request.delete(`/api/leagues/${pk}/`, { headers });
    }
    await context.request.delete(`/api/organizations/${orgPk}/`, { headers });
  }
});
