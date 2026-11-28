import type { BrowserContext, Locator, Page, Request } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginAdmin,
  postWithCsrf,
  resetEventsData,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const PREVIEW_PATH = '/api/events/discord-preview/';

const PERSISTED_SERIES_FIELDS = [
  'name',
  'frequency',
  'day_of_week',
  'time_of_day',
  'discord_create_event',
  'discord_event_title',
] as const;

async function createPreviewSeries(
  context: BrowserContext,
  info: EventInfo,
): Promise<{ id: number }> {
  const name = `Preview Series ${Date.now()}`;
  const resp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, {
    organization: info.orgPk,
    name,
    frequency: 'daily',
    day_of_week: null,
    time_of_day: '20:00:00',
    starts_at: new Date().toISOString().slice(0, 10),
    generate_days_ahead: 3,
    is_active: true,
    tournament_name: `${name} Tournament`,
    tournament_league: info.leaguePk,
    tournament_type: 'single_elimination',
    game_type: 1,
    draft_type: 'shuffle',
    people_per_team: 5,
    number_of_teams: null,
    timezone: 'UTC',
    auto_approve: true,
    max_players: null,
  });
  if (!resp.ok()) {
    throw new Error(
      `Create series failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json();
}

async function persistedSeries(
  context: BrowserContext,
  id: number,
): Promise<Record<string, unknown>> {
  const resp = await context.request.get(`${API_URL}/events/repeaters/${id}/`);
  expect(resp.ok()).toBe(true);
  const body = await resp.json();
  return Object.fromEntries(PERSISTED_SERIES_FIELDS.map((k) => [k, body[k]]));
}

async function scrollViewportOverflow(target: Locator): Promise<number[]> {
  return target.evaluate((el) => {
    const viewport = el.closest('[data-slot="scroll-area-viewport"]');
    if (!viewport) throw new Error('target is not inside a scroll viewport');
    const ring = 3;
    const b = el.getBoundingClientRect();
    const v = viewport.getBoundingClientRect();
    return [
      v.left - (b.left - ring),
      v.top - (b.top - ring),
      b.right + ring - v.right,
      b.bottom + ring - v.bottom,
    ].map((px) => Math.max(0, Math.round(px)));
  });
}

async function openNeedsInputPreview(page: Page, kind: string) {
  const responsePromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === 'POST' &&
      new URL(resp.url()).pathname === PREVIEW_PATH &&
      resp.request().postDataJSON()?.kind === kind,
  );
  await page.getByTestId(`discord-preview-${kind}`).click();
  const response = await responsePromise;
  const dialog = page.getByTestId('discord-preview-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('discord-preview-needs-input')).toBeVisible({
    timeout: 15000,
  });
  return { dialog, request: response.request().postDataJSON(), response };
}

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

  test.afterEach(async ({ context }) => {
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

    const historyUrl = `${API_URL}/events/${eventInfo.pk}/discord/`;
    const historyBefore = await context.request.get(historyUrl);
    expect([200, 404]).toContain(historyBefore.status());
    const history = await historyBefore.json();

    const writes: string[] = [];
    const permissionChecks: Request[] = [];
    page.on('request', (req: Request) => {
      const url = new URL(req.url());
      if (
        req.method() === 'POST' &&
        url.pathname === `/api/events/${eventInfo.pk}/permission-checks/`
      ) {
        permissionChecks.push(req);
        return;
      }
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
    const historyAfter = await context.request.get(historyUrl);
    expect(historyAfter.status()).toBe(historyBefore.status());
    expect(await historyAfter.json()).toEqual(history);
    expect(permissionChecks.length).toBeGreaterThan(0);
    expect(writes).toEqual([]);
  });

  test('series prerequisite navigation preserves edits without writes @cicd', async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000);
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);
    const series = await createPreviewSeries(context, eventInfo);
    const before = await persistedSeries(context, series.id);

    const writes: string[] = [];
    page.on('request', (req: Request) => {
      const url = new URL(req.url());
      if (
        req.method() !== 'GET' &&
        url.pathname.startsWith('/api/events/') &&
        url.pathname !== PREVIEW_PATH &&
        !url.pathname.endsWith('/permission-checks/')
      ) {
        writes.push(`${req.method()} ${url.pathname}`);
      }
    });

    await visitAndWaitForHydration(page, `/event-series/${series.id}`);
    await page.getByTestId('edit-series-btn').click();
    const modal = page.getByTestId('edit-series-modal');
    await expect(modal).toBeVisible();

    const unsavedName = `Unsaved series ${Date.now()}`;
    const nameInput = page.getByTestId('edit-series-name-input');
    await nameInput.fill(unsavedName);
    const frequency = page.getByTestId('edit-series-frequency-select');
    await frequency.click();
    await page.getByTestId('edit-series-frequency-option-weekly').click();
    await expect(frequency).toContainText('Weekly');
    const daySelect = page.getByTestId('edit-series-day-select');
    await expect(daySelect).toContainText('Select day');

    await page.getByTestId('edit-series-tab-discord').click();
    const createToggle = page.getByTestId('discord-discord_create_event');
    if (!(await createToggle.isChecked())) await createToggle.check();
    const unsavedTitle = `Series preview ${Date.now()}`;
    const titleInput = page.getByPlaceholder('Leave blank to use event name');
    await titleInput.fill(unsavedTitle);

    const { dialog, request, response } = await openNeedsInputPreview(
      page,
      'scheduled_event',
    );
    expect(request.context).toEqual({
      type: 'repeater',
      repeater_id: series.id,
    });
    expect(request.values.frequency).toBe('weekly');
    expect(request.values.day_of_week).toBeNull();
    const body = await response.json();
    expect(body.status).toBe('needs_input');
    expect(body.missing).toEqual(['schedule']);

    const scheduleAction = dialog.getByTestId(
      'discord-preview-missing-schedule',
    );
    await scheduleAction.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(scheduleAction).toBeFocused();
    expect(
      await scheduleAction.evaluate((el) => el.matches(':focus-visible')),
    ).toBe(true);
    expect(await scrollViewportOverflow(scheduleAction)).toEqual([0, 0, 0, 0]);
    await page.keyboard.press('Enter');

    await expect(page.getByTestId('discord-preview-dialog')).toHaveCount(0);
    await expect(modal).toBeVisible();
    await expect(page.getByTestId('edit-series-tab-event')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(frequency).toBeFocused();
    await expect(frequency).toContainText('Weekly');
    await expect(nameInput).toHaveValue(unsavedName);
    await expect(daySelect).toContainText('Select day');

    await page.getByTestId('edit-series-tab-discord').click();
    await expect(titleInput).toHaveValue(unsavedTitle);
    await expect(createToggle).toBeChecked();

    await page.getByTestId('modal-cancel-button').click();
    await expect(modal).toHaveCount(0);

    expect(await persistedSeries(context, series.id)).toEqual(before);
    expect(writes).toEqual([]);
  });

  test('later preview dismissal does not repeat prerequisite navigation', async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000);
    const eventInfo = await getEventsTestData(context);
    await loginAdmin(context);
    const series = await createPreviewSeries(context, eventInfo);
    const before = await persistedSeries(context, series.id);
    const writes: string[] = [];
    page.on('request', (req: Request) => {
      const { pathname } = new URL(req.url());
      if (
        req.method() !== 'GET' &&
        pathname.startsWith('/api/events/') &&
        pathname !== PREVIEW_PATH &&
        !pathname.endsWith('/permission-checks/')
      ) {
        writes.push(`${req.method()} ${pathname}`);
      }
    });

    await visitAndWaitForHydration(page, `/event-series/${series.id}`);
    await page.getByTestId('edit-series-btn').click();
    const modal = page.getByTestId('edit-series-modal');
    await page.getByTestId('edit-series-frequency-select').click();
    await page.getByTestId('edit-series-frequency-option-weekly').click();
    await expect(page.getByTestId('edit-series-day-select')).toContainText(
      'Select day',
    );
    const discordTab = page.getByTestId('edit-series-tab-discord');
    await discordTab.click();
    await page.getByTestId('discord-discord_create_event').check();

    const { dialog } = await openNeedsInputPreview(page, 'scheduled_event');
    await dialog.getByTestId('discord-preview-missing-schedule').focus();
    await page.keyboard.press('Space');
    await expect(page.getByTestId('discord-preview-dialog')).toHaveCount(0);
    await expect(modal).toBeVisible();
    await expect(page.getByTestId('edit-series-tab-event')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(
      page.getByTestId('edit-series-frequency-select'),
    ).toBeFocused();

    await discordTab.click();
    const previewTrigger = page.getByTestId('discord-preview-scheduled_event');
    for (const dismissal of ['Escape', 'Close']) {
      const reopened = await openNeedsInputPreview(page, 'scheduled_event');
      if (dismissal === 'Escape') {
        await page.keyboard.press('Escape');
      } else {
        await reopened.dialog.getByTestId('dialog-close-button').click();
      }
      await expect(page.getByTestId('discord-preview-dialog')).toHaveCount(0);
      await expect(modal).toBeVisible();
      await expect(discordTab).toHaveAttribute('aria-selected', 'true');
      await expect(previewTrigger).toBeVisible();
      await expect(previewTrigger).toBeFocused();
      expect(writes).toEqual([]);
    }

    await page.getByTestId('modal-cancel-button').click();
    await expect(modal).toHaveCount(0);
    expect(await persistedSeries(context, series.id)).toEqual(before);
    expect(writes).toEqual([]);
  });
});
