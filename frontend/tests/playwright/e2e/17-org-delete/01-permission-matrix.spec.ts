/**
 * Organization Delete — Permission Matrix
 *
 * Verifies that only the org owner sees the Danger Zone section and that
 * the delete dialog input-gate works correctly. Admins, staff, and plain
 * members must not see the Danger Zone at all.
 *
 * The owner test deliberately does NOT submit the delete — that would remove
 * the org and pollute subsequent runs. The API-level destroy success path is
 * covered by backend unit tests (Task 14).
 *
 * PKs match backend/tests/data/org_delete.py.
 */

import { test, expect } from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';

const ORG_DELETE_OWNER_PK = 6000;
const ORG_DELETE_ADMIN_PK = 6001;
const ORG_DELETE_STAFF_PK = 6002;
const ORG_DELETE_MEMBER_PK = 6003;
const ORG_DELETE_ORG_NAME = 'Org Delete Test Org';

let orgPk: number;

test.describe('Organization delete — permission matrix', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const resp = await context.request.get('https://localhost/api/organizations/');
    const data = await resp.json();
    const list = Array.isArray(data) ? data : (data.results ?? []);
    const org = list.find((o: { name: string }) => o.name === ORG_DELETE_ORG_NAME);
    if (!org) {
      throw new Error(
        `Org "${ORG_DELETE_ORG_NAME}" not found. Run: just db::populate::all`
      );
    }
    orgPk = org.pk;
    await context.close();
  });

  test('org_owner sees Danger Zone and dialog input gate works', async ({ context, page }) => {
    await loginAsUser(context, ORG_DELETE_OWNER_PK);
    await page.goto(`/organizations/${orgPk}`);

    await expect(page.getByTestId('org-danger-zone')).toBeVisible();
    await expect(page.getByTestId('org-danger-zone-trigger')).toBeVisible();

    await page.getByTestId('org-danger-zone-trigger').click();
    await expect(page.getByTestId('delete-organization-dialog')).toBeVisible();
    await expect(page.getByTestId('delete-organization-confirm')).toBeDisabled();

    await page.getByTestId('delete-organization-confirm-input').fill('not the right name');
    await expect(page.getByTestId('delete-organization-confirm')).toBeDisabled();

    await page.getByTestId('delete-organization-confirm-input').fill(ORG_DELETE_ORG_NAME);
    await expect(page.getByTestId('delete-organization-confirm')).toBeEnabled();

    // Do NOT click confirm — closing verifies the dialog dismisses cleanly.
    await page.getByTestId('delete-organization-cancel').click();
    await expect(page.getByTestId('delete-organization-dialog')).not.toBeVisible();
  });

  test('org_admin does NOT see Danger Zone', async ({ context, page }) => {
    await loginAsUser(context, ORG_DELETE_ADMIN_PK);
    await page.goto(`/organizations/${orgPk}`);
    await expect(page.getByTestId('org-danger-zone')).toHaveCount(0);
  });

  test('org_staff does NOT see Danger Zone', async ({ context, page }) => {
    await loginAsUser(context, ORG_DELETE_STAFF_PK);
    await page.goto(`/organizations/${orgPk}`);
    await expect(page.getByTestId('org-danger-zone')).toHaveCount(0);
  });

  test('org_member does NOT see Danger Zone', async ({ context, page }) => {
    await loginAsUser(context, ORG_DELETE_MEMBER_PK);
    await page.goto(`/organizations/${orgPk}`);
    await expect(page.getByTestId('org-danger-zone')).toHaveCount(0);
  });
});
