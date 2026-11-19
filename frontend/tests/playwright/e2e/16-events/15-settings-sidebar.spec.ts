/**
 * Settings sidebar E2E tests
 *
 * The full-screen event settings dialogs (SettingsDialog via EventFormDialog):
 * category sidebar, settings search, jump-to-field, and the phone layout.
 * Exercised through the org page's Create Event modal (Events Test Org).
 */

import type { Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  resetEventsData,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';

let eventInfo: EventInfo;

const P = 'event-modal';

async function openCreateEvent(page: Page, mobile = false) {
  await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
  if (mobile) {
    await page.getByTestId('page-nav-trigger').click();
    await page.getByTestId('page-nav-events').click();
  } else {
    await page.getByTestId('org-tab-events').click();
  }
  await page.getByTestId('create-event-btn').click();
  await expect(
    page.getByRole('heading', { name: 'Create Event' }),
  ).toBeVisible();
}

test.describe('Events - Settings sidebar (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('desktop: categories are vertical tabs in a sidebar', async ({
    page,
  }) => {
    await openCreateEvent(page);

    const sidebar = page.getByTestId(`${P}-sidebar`);
    await expect(sidebar).toBeVisible();
    await expect(sidebar.getByRole('tablist')).toHaveAttribute(
      'aria-orientation',
      'vertical',
    );
    await expect(page.getByTestId(`${P}-tab-event`)).toHaveAttribute(
      'data-state',
      'active',
    );

    await page.getByTestId(`${P}-tab-lobby`).click();
    await expect(page.getByTestId(`${P}-tab-lobby`)).toHaveAttribute(
      'data-state',
      'active',
    );

    // Arrow keys move between categories.
    await page.keyboard.press('ArrowDown');
    await expect(page.getByTestId(`${P}-tab-approval`)).toBeFocused();
  });

  test('search filters categories and jumps to a field', async ({ page }) => {
    await openCreateEvent(page);

    // Dialog auto-focuses the first input, where "/" is just a character.
    await page.getByRole('heading', { name: 'Create Event' }).click();
    await page.keyboard.press('/');
    const search = page.getByTestId(`${P}-search`);
    await expect(search).toBeFocused();

    await search.fill('tournament name');
    await expect(page.getByTestId(`${P}-tab-tournament`)).toBeVisible();
    await expect(page.getByTestId(`${P}-tab-discord`)).toHaveCount(0);
    await expect(page.getByTestId(`${P}-tab-lobby`)).toHaveCount(0);
    // The active category stays listed even when it doesn't match.
    await expect(page.getByTestId(`${P}-tab-event`)).toHaveAttribute(
      'data-state',
      'active',
    );

    const hit = page.getByTestId(`${P}-search-hit`).filter({
      has: page.locator('span', { hasText: /^Tournament Name$/ }),
    });
    await hit.click();

    await expect(page.getByTestId(`${P}-tab-tournament`)).toHaveAttribute(
      'data-state',
      'active',
    );
    const input = page.getByTestId('event-tournament-name-input');
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();
  });

  test('keyword search reaches the lazy Discord category', async ({ page }) => {
    await openCreateEvent(page);

    await page.getByTestId(`${P}-search`).fill('announcement');
    await expect(page.getByTestId(`${P}-tab-discord`)).toBeVisible();
    await expect(page.getByTestId(`${P}-tab-lobby`)).toHaveCount(0);
  });

  test('Enter in search jumps instead of submitting; Escape clears without closing', async ({
    page,
  }) => {
    let posted = false;
    page.on('request', (req) => {
      if (req.url().includes('/api/events') && req.method() === 'POST') {
        posted = true;
      }
    });
    await openCreateEvent(page);

    const search = page.getByTestId(`${P}-search`);
    await search.fill('tournament name');
    await search.press('Enter');
    await expect(page.getByTestId(`${P}-tab-tournament`)).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page.getByTestId('event-tournament-name-input')).toBeFocused();

    await search.fill('zzz-no-such-setting');
    await expect(page.getByTestId(`${P}-search-empty`)).toBeVisible();
    await search.press('Escape');
    await expect(search).toHaveValue('');
    await expect(
      page.getByRole('heading', { name: 'Create Event' }),
    ).toBeVisible();
    await expect(page.getByTestId(`${P}-tab-event`)).toBeVisible();
    expect(posted).toBe(false);
  });

  test('marks the category holding an invalid field', async ({ page }) => {
    await openCreateEvent(page);

    await page.getByTestId('event-name-input').fill('');
    await page.getByTestId(`${P}-tab-lobby`).click();
    await page.getByTestId('form-dialog-submit').click();

    await expect(page.getByTestId(`${P}-tab-event`)).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page.getByTestId(`${P}-tab-event`)).toHaveAttribute(
      'data-invalid',
      'true',
    );
    await expect(page.getByTestId(`${P}-tab-lobby`)).not.toHaveAttribute(
      'data-invalid',
      'true',
    );
  });

  test('phone: search above a horizontal category strip', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await openCreateEvent(page, true);

    await expect(page.getByTestId(`${P}-sidebar`)).toHaveCount(0);
    const tabs = page.getByRole('tablist');
    await expect(tabs).not.toHaveAttribute('aria-orientation', 'vertical');

    await page.getByTestId(`${P}-search`).fill('tournament name');
    const hit = page.getByTestId(`${P}-search-hit`).filter({
      has: page.locator('span', { hasText: /^Tournament Name$/ }),
    });
    await expect(hit).toContainText('Tournament');
    await hit.click();

    await expect(page.getByTestId(`${P}-tab-tournament`)).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(
      page.getByTestId('event-tournament-name-input'),
    ).toBeInViewport();

    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(overflow, 'horizontal overflow with the settings dialog open').toBe(
      false,
    );
  });
});
