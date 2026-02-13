import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

/** Editable field names matching data-testid="edit-user-{field}" */
export type EditUserField = 'nickname' | 'mmr' | 'steam_account_id' | 'guildNickname';

/**
 * Click the edit button on a user card to open the edit modal.
 *
 * @param page - Playwright Page instance
 * @param userCard - Locator for the user card element
 */
export async function openEditModal(page: Page, userCard: Locator): Promise<void> {
  const editBtn = userCard.locator('[data-testid="edit-user-btn"]');
  await expect(editBtn).toBeVisible({ timeout: 5000 });
  await editBtn.click();
  await expect(page.locator('[data-testid="edit-user-nickname"]')).toBeVisible({ timeout: 5000 });
}

/**
 * Read the current value of an edit form field.
 *
 * @param page - Playwright Page instance
 * @param field - The field name to read
 * @returns The current input value
 */
export async function readEditField(page: Page, field: EditUserField): Promise<string> {
  const input = page.locator(`[data-testid="edit-user-${field}"]`);
  await expect(input).toBeVisible({ timeout: 5000 });
  return input.inputValue();
}

/**
 * Fill a specific field in the edit modal.
 *
 * @param page - Playwright Page instance
 * @param field - The field name to fill
 * @param value - The value to set
 */
export async function fillEditField(page: Page, field: EditUserField, value: string): Promise<void> {
  const input = page.locator(`[data-testid="edit-user-${field}"]`);
  await input.click();
  await input.fill(value);
}

/**
 * Click the Save Changes button and wait for the PATCH to complete.
 *
 * The edit modal uses e.preventDefault() in its DialogClose handler,
 * so the dialog stays open after save. This helper waits for the PATCH
 * response, then closes the dialog via Escape.
 *
 * @param page - Playwright Page instance
 */
export async function saveEditModal(page: Page): Promise<void> {
  // Set up response listener BEFORE clicking save
  const patchResponse = page.waitForResponse(
    (resp) => resp.request().method() === 'PATCH' && /\/users\//.test(resp.url()),
    { timeout: 15000 },
  );

  const saveBtn = page.getByRole('button', { name: 'Save Changes' });
  await saveBtn.click();

  // Wait for the PATCH to complete
  const response = await patchResponse;
  expect(response.status()).toBe(200);

  // Wait for isSubmitting to reset (button returns from "Saving..." to "Save Changes")
  // so the next modal open doesn't inherit stale submitting state.
  await expect(saveBtn).toBeVisible({ timeout: 5000 });

  // Dialog stays open due to e.preventDefault() in DialogClose — close via Escape
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300); // Let close animation finish
}

/**
 * Full edit flow: open modal, read old value, fill new value, save.
 * Returns the original value for later restoration.
 *
 * @param page - Playwright Page instance
 * @param userCard - Locator for the user card element
 * @param field - The field name to edit
 * @param newValue - The new value to set
 * @returns The original field value before editing
 */
export async function editUserField(
  page: Page,
  userCard: Locator,
  field: EditUserField,
  newValue: string,
): Promise<string> {
  await openEditModal(page, userCard);
  const originalValue = await readEditField(page, field);
  await fillEditField(page, field, newValue);
  await saveEditModal(page);
  return originalValue;
}

/**
 * Restore a field to its original value by re-opening the edit modal.
 *
 * @param page - Playwright Page instance
 * @param userCard - Locator for the user card element
 * @param field - The field name to restore
 * @param originalValue - The original value to restore
 */
export async function restoreUserField(
  page: Page,
  userCard: Locator,
  field: EditUserField,
  originalValue: string,
): Promise<void> {
  await openEditModal(page, userCard);
  await fillEditField(page, field, originalValue || '0');
  await saveEditModal(page);
}
