import type { Page, Request } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginAdmin,
  resetEventsData,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const PREVIEW_PATH = '/api/events/discord-preview/';

async function openDiscordTab(page: Page, eventPk: number): Promise<void> {
  await visitAndWaitForHydration(page, `/events/${eventPk}`);
  await expect(page.getByTestId('event-edit-btn')).toBeVisible({
    timeout: 15000,
  });
  await page.getByTestId('event-edit-btn').click();
  await page.getByTestId('edit-event-tab-discord').click();
}

async function openPreview(page: Page, kind: string) {
  await page.getByTestId(`discord-preview-${kind}`).click();
  const dialog = page.getByTestId('discord-preview-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('discord-preview-loading')).toHaveCount(0, {
    timeout: 15000,
  });
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  await expect(dialog.getByTestId('discord-preview-gate')).toBeVisible();
  await expect(
    dialog
      .getByTestId('discord-message-preview')
      .or(dialog.getByTestId('discord-scheduled-event'))
      .or(dialog.getByTestId('discord-preview-start-mention-header'))
      .first(),
  ).toBeVisible();
  return dialog;
}

async function closePreview(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('discord-preview-dialog')).toHaveCount(0);
}

test.describe('Discord message preview @cicd', () => {
  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('previews follow unsaved edits and never write', async ({
    page,
    context,
  }) => {
    // Opens every preview dialog in turn; the default 30s budget is too small.
    test.setTimeout(90_000);
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);
    const before = await (
      await context.request.get(`${API_URL}/events/${eventInfo.pk}/`)
    ).json();

    const writes: string[] = [];
    page.on('request', (req: Request) => {
      const url = new URL(req.url());
      if (
        req.method() !== 'GET' &&
        url.pathname.startsWith('/api/events/') &&
        url.pathname !== PREVIEW_PATH
      ) {
        writes.push(`${req.method()} ${url.pathname}`);
      }
    });

    await openDiscordTab(page, eventInfo.pk);

    let dialog = await openPreview(page, 'signup_post');
    await expect(dialog.getByRole('heading')).toContainText('Signup post');
    await expect(dialog).toContainText(before.name);
    await closePreview(page);

    const createToggle = page.getByTestId('discord-discord_create_event');
    if (!(await createToggle.isChecked())) await createToggle.check();
    const unsavedTitle = `Preview ${Date.now()}`;
    await page
      .getByPlaceholder('Leave blank to use event name')
      .fill(unsavedTitle);

    dialog = await openPreview(page, 'signup_post');
    await expect(dialog).toContainText(unsavedTitle);
    await expect(dialog.locator(':focus')).toHaveCount(1);
    await closePreview(page);
    await expect(page.getByTestId('edit-event-modal')).toBeVisible();

    dialog = await openPreview(page, 'scheduled_event');
    await expect(dialog.getByTestId('discord-scheduled-event')).toBeVisible();
    await expect(dialog).toContainText(unsavedTitle);
    await closePreview(page);

    dialog = await openPreview(page, 'start_mention');
    await closePreview(page);

    const buttons = page.locator('[data-testid^="discord-preview-"]');
    const ids = await buttons.evaluateAll((els) =>
      els
        .map((el) => el.getAttribute('data-testid') ?? '')
        .filter((id) => id !== 'discord-preview-disabled-trigger'),
    );
    expect(ids.length).toBeGreaterThan(5);
    for (const id of ids) {
      await openPreview(page, id.replace('discord-preview-', ''));
      await closePreview(page);
    }

    await expect(page.getByTestId('edit-event-modal')).toBeVisible();
    await page.getByTestId('modal-cancel-button').click();
    await expect(page.getByTestId('edit-event-modal')).toHaveCount(0);

    await page.getByTestId('event-edit-btn').click();
    await page.getByTestId('edit-event-tab-discord').click();
    const reopenedToggle = page.getByTestId('discord-discord_create_event');
    if (before.discord_create_event) {
      await expect(
        page.getByPlaceholder('Leave blank to use event name'),
      ).toHaveValue(before.discord_event_title ?? '');
    } else {
      await expect(reopenedToggle).not.toBeChecked();
    }
    await page.getByTestId('modal-cancel-button').click();

    const after = await (
      await context.request.get(`${API_URL}/events/${eventInfo.pk}/`)
    ).json();
    expect(after.discord_event_title).toBe(before.discord_event_title);
    expect(after.discord_create_event).toBe(before.discord_create_event);
    expect(writes).toEqual([]);
  });
});
