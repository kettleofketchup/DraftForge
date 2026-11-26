/**
 * Creating an organization adds it to the /organizations list without a reload.
 */

import { expect, test } from '../../fixtures';
import { loginUser } from '../../fixtures/auth';
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';

test('new organization appears in the list without a reload', async ({
  context,
  page,
}) => {
  await loginUser(context);
  const name = `Rerender Org ${Date.now()}`;

  await page.goto('/organizations');
  await expect(page.getByTestId('create-organization-button')).toBeVisible();
  await expect(page.getByText(name)).toHaveCount(0);

  let reloaded = false;
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) reloaded = true;
  });

  await page.getByTestId('create-organization-button').click();
  await page.getByPlaceholder('Organization name').fill(name);
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/organizations/') &&
      r.request().method() === 'POST',
  );
  await page.getByTestId('form-dialog-submit').click();
  const orgPk = (await (await created).json()).pk as number;

  try {
    await expect(page.getByText(name)).toBeVisible();
    expect(reloaded).toBe(false);
  } finally {
    await context.request.delete(`${API_URL}/organizations/${orgPk}/`, {
      headers: { 'X-CSRFToken': await getCsrfToken(context) },
    });
  }
});
