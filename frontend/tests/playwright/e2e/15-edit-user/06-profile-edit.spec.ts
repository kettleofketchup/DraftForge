/**
 * Edit Profile Modal
 *
 * @cicd smoke test verifying that a logged-in user can open their profile
 * edit modal, update position preferences, save, and verify the change
 * appears in the UI.
 *
 * Uses the admin user (PK 1001, kettleofketchup) — edits only that user's
 * own profile positions and restores original values afterward.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
} from '../../fixtures';

const ADMIN_PK = 1001;

test.describe('Edit Profile Modal (@cicd)', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: edit position preference via profile edit modal', async ({ page }) => {
    // Navigate to the admin user's profile page
    await visitAndWaitForHydration(page, `/user/${ADMIN_PK}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Click the edit profile button (EditIconButton with sr-only text "Edit Profile")
    const editBtn = page.getByRole('button', { name: 'Edit Profile' });
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for the edit profile modal to appear
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    await expect(dialog.getByText('Edit Profile').first()).toBeVisible();

    // The PositionForm renders Carry as the first Select inside "Edit Positions".
    // Locate the first combobox (Carry) inside the modal.
    const carryTrigger = dialog.locator('button[role="combobox"]').first();
    await expect(carryTrigger).toBeVisible({ timeout: 5000 });

    // Read the current carry value text from the trigger
    const originalCarryText = (await carryTrigger.textContent())?.trim() ?? '';

    // Determine a new value: toggle between "1: Favorite" and "2: Can play"
    const isCurrentlyFavorite = originalCarryText.includes('1:');
    const newOptionText = isCurrentlyFavorite ? '2: Can play' : '1: Favorite';

    // Click the carry select trigger to open the dropdown
    await carryTrigger.click();

    // Select the new option from the dropdown
    const option = page.getByRole('option', { name: newOptionText });
    await expect(option).toBeVisible({ timeout: 5000 });
    await option.click();

    // Wait for the select dropdown to close
    await page.waitForTimeout(300);

    // Set up response listener BEFORE clicking save
    const postResponse = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes('/profile_update'),
      { timeout: 15000 },
    );

    // Click Save Changes
    const saveBtn = dialog.getByRole('button', { name: 'Save Changes' });
    await expect(saveBtn).toBeVisible({ timeout: 5000 });
    await saveBtn.click();

    // Wait for the POST to complete with 201
    const response = await postResponse;
    expect(response.status()).toBe(201);

    // The modal closes automatically on success
    await expect(dialog).not.toBeVisible({ timeout: 5000 });

    // Verify the toast success message appeared
    await expect(page.getByText('Profile updated successfully')).toBeVisible({
      timeout: 5000,
    });

    // Verify the Positions card is visible in the overview tab
    // (confirms the page re-rendered with updated data)
    const positionsHeading = page.getByRole('heading', { name: 'Positions' });
    await expect(positionsHeading).toBeVisible({ timeout: 5000 });

    // --- Restore original value ---
    await editBtn.click();
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Find the first combobox (Carry) again
    const carryTriggerRestore = dialog.locator('button[role="combobox"]').first();
    await expect(carryTriggerRestore).toBeVisible({ timeout: 5000 });

    // Determine the restore option text from the original value
    let restoreOptionText: string;
    if (originalCarryText.includes('0:') || originalCarryText.includes("Don't show")) {
      restoreOptionText = "0: Don't show this role";
    } else if (originalCarryText.includes('1:')) {
      restoreOptionText = '1: Favorite';
    } else if (originalCarryText.includes('2:')) {
      restoreOptionText = '2: Can play';
    } else if (originalCarryText.includes('3:')) {
      restoreOptionText = '3: If the team needs';
    } else if (originalCarryText.includes('4:')) {
      restoreOptionText = '4: I would rather not but I guess';
    } else if (originalCarryText.includes('5:')) {
      restoreOptionText = '5: Least Favorite';
    } else {
      // Default: if no position was set, the placeholder might show "0: Don't show"
      restoreOptionText = "0: Don't show this role";
    }

    await carryTriggerRestore.click();
    const restoreOption = page.getByRole('option', { name: restoreOptionText });
    await expect(restoreOption).toBeVisible({ timeout: 5000 });
    await restoreOption.click();
    await page.waitForTimeout(300);

    // Save the restoration
    const restoreResponsePromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        resp.url().includes('/profile_update'),
      { timeout: 15000 },
    );

    const saveBtnRestore = dialog.getByRole('button', { name: 'Save Changes' });
    await saveBtnRestore.click();

    const restoreResp = await restoreResponsePromise;
    expect(restoreResp.status()).toBe(201);

    // Verify modal closes after restoration
    await expect(dialog).not.toBeVisible({ timeout: 5000 });
  });
});
