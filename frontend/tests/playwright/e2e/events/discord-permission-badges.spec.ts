import type { BrowserContext, Locator, Page } from '@playwright/test';
import type { PermissionChecksResponse } from '../../../../app/features/discord-permissions/schemas';
import {
  expect,
  loginAsUser,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import {
  getDiscordPermissionsData,
  resetDiscordPermissions,
  setDiscordPermissionScenario,
  type DiscordPermissionsData,
} from '../../fixtures/discord-permissions';

let data: DiscordPermissionsData;
let requests: string[];

function badge(scope: Page | Locator, key: string): Locator {
  return scope.getByTestId(`discord-permission-badge-${key}`);
}

async function expectFullyInside(content: Locator, container: Locator) {
  await expect
    .poll(async () => {
      const inner = await content.boundingBox();
      const outer = await container.boundingBox();
      return (
        !!inner &&
        !!outer &&
        inner.y >= outer.y &&
        inner.y + inner.height <= outer.y + outer.height &&
        inner.x >= outer.x &&
        inner.x + inner.width <= outer.x + outer.width
      );
    })
    .toBe(true);
}

async function expectPaddedScroll(panel: Locator) {
  const outer = (await panel.boundingBox())!;
  const title = (await panel
    .getByTestId('discord-permission-details-title')
    .boundingBox())!;
  const scroll = (await panel
    .getByTestId('discord-permission-details-scroll')
    .boundingBox())!;
  expect(scroll.y).toBeGreaterThanOrEqual(title.y + title.height + 8);
  expect(scroll.y + scroll.height).toBeLessThanOrEqual(
    outer.y + outer.height - 8,
  );
  expect(scroll.x).toBeGreaterThanOrEqual(outer.x + 12);
  expect(scroll.x + scroll.width).toBeLessThanOrEqual(
    outer.x + outer.width - 12,
  );
}

async function expectNeutral(target: Locator) {
  expect(
    await target.evaluate((element) =>
      [element, ...element.querySelectorAll('*')].some((node) =>
        node.classList.contains('text-success'),
      ),
    ),
  ).toBe(false);
}

async function state(page: Page, eventId = data.fresh_event_pk) {
  await visitAndWaitForHydration(page, `/events/${eventId}`);
  await page.getByTestId('event-tab-discord').click();
  await expect(page.getByTestId('discord-permission-checks')).toBeVisible();
  return page.getByTestId('discord-permission-checks');
}

async function edit(page: Page, eventId: number) {
  await visitAndWaitForHydration(page, `/events/${eventId}`);
  await page.getByTestId('event-edit-btn').click();
  await page.getByTestId('edit-event-tab-discord').click();
  return page.getByTestId('edit-event-modal');
}

async function channelChoices(page: Page) {
  await page.route(
    `**/api/discord/organizations/${data.org_pk}/channels/**`,
    (route) =>
      route.fulfill({
        json: {
          channels: [
            {
              id: data.channel_ids.attendance,
              name: 'attendance',
              type: 0,
              type_label: 'Text',
            },
            {
              id: data.channel_ids.announcement,
              name: 'announcements',
              type: 0,
              type_label: 'Text',
            },
          ],
        },
      }),
  );
}

async function savedChecks(context: BrowserContext, eventId: number) {
  const response = await context.request.get(
    `${API_URL}/events/${eventId}/permission-checks/`,
  );
  expect(response.status()).toBe(200);
  return ((await response.json()) as PermissionChecksResponse).checks;
}

test.describe('Discord permission badges @cicd', () => {
  test.beforeEach(async ({ context, page }) => {
    data = await resetDiscordPermissions(context);
    await loginAsUser(context, data.staff_pk);
    requests = [];
    page.on('request', (request) => requests.push(request.url()));
  });

  test.afterEach(async ({ context }) => {
    expect(requests.filter((url) => /\/fire\//.test(url))).toEqual([]);
    expect((await getDiscordPermissionsData(context)).message_log_count).toBe(
      data.message_log_count,
    );
  });

  test('fresh Discord State checks actual destinations without history', async ({
    page,
    context,
  }) => {
    const checks = await state(page);
    await expect(badge(checks, 'attendance_reminder')).toHaveText(
      'Missing permissions',
    );
    await expect(badge(checks, 'announcement')).toHaveText(
      'Permissions verified',
    );
    await badge(checks, 'attendance_reminder').click();
    const details = page.getByTestId(
      'discord-permission-details-attendance_reminder',
    );
    await expect(details).toContainText('Embed Links');
    await expect(details).toContainText('Granted permissions');
    await expect(details).toContainText('(configured)');
    await page.keyboard.press('Escape');
    const history = await context.request.get(
      `${API_URL}/events/${data.fresh_event_pk}/discord/`,
    );
    expect(history.status()).toBe(404);
    const results = await savedChecks(context, data.fresh_event_pk);
    expect(
      results.find((check) => check.key === 'attendance_reminder')?.destination
        .channel_id,
    ).toBe(data.channel_ids.attendance);
    await expect(badge(checks, 'mark_interested')).toHaveText(
      'Unsupported operation',
    );
    await expect(badge(checks, 'signup_reminder')).toHaveText(
      'Recipient dependent',
    );
    await expectNeutral(badge(checks, 'mark_interested'));
    await expectNeutral(badge(checks, 'signup_reminder'));
  });

  test('saving with red badges succeeds and clearing the own channel previews the announcement fallback', async ({
    page,
    context,
  }) => {
    const modal = await edit(page, data.posted_event_pk);
    await expect(badge(modal, 'attendance_reminder')).toHaveText(
      '1 setting blocked',
    );
    const saved = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/events/${data.posted_event_pk}/`) &&
        response.request().method() === 'PATCH',
    );
    await modal.getByTestId('form-dialog-submit').click();
    expect((await saved).ok()).toBeTruthy();
    await expect(modal).not.toBeVisible();

    const reopened = await edit(page, data.posted_event_pk);
    await expect(badge(reopened, 'attendance_reminder')).toHaveText(
      '1 setting blocked',
    );
    const preview = page.waitForResponse(
      (response) =>
        response
          .url()
          .includes(`/api/events/${data.posted_event_pk}/permission-checks/`) &&
        response.request().method() === 'POST' &&
        (response.request().postData() ?? '').includes('attendance_reminder') &&
        !(response.request().postData() ?? '').includes(
          data.channel_ids.attendance,
        ),
    );
    await reopened
      .getByTestId('discord-confirm-attendance-channel-select-clear')
      .click();
    const previewed = (await (
      await preview
    ).json()) as PermissionChecksResponse;
    const fallback = previewed.checks.find(
      (check) => check.key === 'attendance_reminder',
    );
    expect(fallback?.destination.channel_id).toBe(
      data.channel_ids.announcement,
    );
    await expect(badge(reopened, 'attendance_reminder')).toHaveCount(0);
    await expect(
      reopened.getByTestId('discord-permission-shared-attendance_reminder'),
    ).toHaveText('Permissions shown on Announcement channel.');
    await expect(badge(reopened, 'announcement')).toHaveText(
      'Permissions verified',
    );
    await badge(reopened, 'announcement').click();
    const panel = page.getByRole('dialog', {
      name: 'Announcement channel permission details',
    });
    await expect(panel).toContainText(
      'Post attendance reminder in Discord (no channel of its own; uses this one) can post here.',
    );
    await expect(
      panel.getByTestId('discord-permission-details-attendance_reminder'),
    ).toContainText(`#${fallback?.destination.name} (fallback)`);
    const unchanged = await context.request.get(
      `${API_URL}/events/${data.posted_event_pk}/`,
    );
    expect((await unchanged.json()).discord_confirm_attendance_channel_id).toBe(
      data.channel_ids.attendance,
    );
  });

  test('scheduled-event creation is independent of posting and own-event updates', async ({
    page,
    context,
  }) => {
    await setDiscordPermissionScenario(context, 'no_create_events');
    const checks = await state(page, data.posted_event_pk);
    await expect(badge(checks, 'scheduled_event_create')).toHaveText(
      'Missing permissions',
    );
    await expect(badge(checks, 'announcement')).toHaveText(
      'Permissions verified',
    );
    await expect(badge(checks, 'scheduled_event_update')).toHaveText(
      'Permissions verified',
    );
    await badge(checks, 'scheduled_event_create').click();
    await expect(
      page.getByTestId('discord-permission-details-scheduled_event_create'),
    ).toContainText('Create Events');
  });

  test('historical Posted stays neutral when current edit access is denied', async ({
    page,
    context,
  }) => {
    await setDiscordPermissionScenario(context, 'edit_access_denied');
    const checks = await state(page, data.posted_event_pk);
    await expect(badge(checks, 'signup_edit')).toHaveText(
      'Missing permissions',
    );
    await expect(badge(checks, 'announcement')).toHaveText(
      'Permissions verified',
    );
    const posted = page.getByTestId('discord-message-status-signup');
    await expect(posted).toHaveText('Posted');
    await expectNeutral(posted);
    await badge(checks, 'signup_edit').click();
    const details = page.getByTestId('discord-permission-details-signup_edit');
    await expect(details).toContainText('View Channel');
    await expect(details).toContainText('(posted)');
    const results = await savedChecks(context, data.posted_event_pk);
    expect(
      results.find((check) => check.key === 'signup_edit')?.destination
        .channel_id,
    ).toBe(data.channel_ids.historical_thread);
  });

  test('failed Recheck discards old green and recovers on the real endpoint', async ({
    page,
    context,
  }) => {
    await setDiscordPermissionScenario(context, 'all_granted');
    const checks = await state(page);
    await expect(badge(checks, 'attendance_reminder')).toHaveText(
      'Permissions verified',
    );
    await setDiscordPermissionScenario(context, 'upstream_unavailable');
    await checks.getByTestId('discord-permission-recheck').click();
    await expect(badge(checks, 'attendance_reminder')).toHaveText(
      'Unable to verify',
    );
    await expect(checks).not.toContainText('Permissions verified');
    await badge(checks, 'attendance_reminder').click();
    const details = page.getByTestId(
      'discord-permission-details-attendance_reminder',
    );
    await expect(details).toContainText('Discord could not be reached');
    await expect(details).not.toContainText('Granted permissions');
    await page.keyboard.press('Escape');
    await setDiscordPermissionScenario(context, 'all_granted');
    await checks.getByTestId('discord-permission-recheck').click();
    await expect(badge(checks, 'attendance_reminder')).toHaveText(
      'Permissions verified',
    );
  });

  test('league-only staff can check event destinations but not organization previews', async ({
    page,
    context,
  }) => {
    await loginAsUser(context, data.league_staff_pk);
    const checks = await state(page);
    await expect(badge(checks, 'attendance_reminder')).toHaveText(
      'Missing permissions',
    );
    const response = await postWithCsrf(
      context,
      `${API_URL}/discord/organizations/${data.org_pk}/permission-checks/`,
      {
        checks: [
          {
            key: 'announcement',
            action: 'announcement',
            channel_id: data.channel_ids.announcement,
          },
        ],
      },
    );
    expect(response.status()).toBe(403);
  });

  test('outsiders receive no event or organization permission data', async ({
    page,
    context,
  }) => {
    await loginAsUser(context, data.outsider_pk);
    await visitAndWaitForHydration(page, `/events/${data.fresh_event_pk}`);
    await expect(page.getByTestId('event-tab-discord')).toHaveCount(0);
    await expect(page.getByTestId('discord-permission-checks')).toHaveCount(0);
    const url = `${API_URL}/events/${data.fresh_event_pk}/permission-checks/`;
    const body = {
      checks: [
        {
          key: 'announcement',
          action: 'announcement',
          channel_id: data.channel_ids.announcement,
        },
      ],
    };
    for (const response of [
      await context.request.get(url),
      await postWithCsrf(context, url, body),
      await postWithCsrf(
        context,
        `${API_URL}/discord/organizations/${data.org_pk}/permission-checks/`,
        body,
      ),
    ]) {
      expect(response.status()).toBe(403);
      expect(await response.json()).not.toHaveProperty('checks');
    }
  });
  test('compact badges share one hover, click and keyboard details panel', async ({
    page,
  }) => {
    const checks = await state(page);
    const trigger = badge(checks, 'attendance_reminder');
    await expect(trigger).toHaveAttribute('type', 'button');
    await expect(trigger).toHaveClass(/py-0\.5/);
    const details = page.getByRole('dialog', {
      name: 'attendance reminder permission details',
    });
    await trigger.hover();
    await expect(details).toBeVisible();
    await details.hover();
    await expect(details).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(details).toBeHidden();
    await trigger.focus();
    await expect(details).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(details).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(details).toBeHidden();
    await expect(trigger).toBeFocused();
    await page.keyboard.press('Space');
    await expect(details).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(details).toBeHidden();
    await trigger.click();
    await expect(details).toBeVisible();
    await page.mouse.click(5, 100);
    await expect(details).toBeHidden();
  });
  for (const edge of ['start', 'end'] as const) {
    test(`State details stay inside a short viewport with a trigger at the ${edge}`, async ({
      page,
    }) => {
      const checks = await state(page);
      await page.setViewportSize({ width: 390, height: 500 });
      const trigger = badge(checks, 'attendance_reminder');
      await trigger.evaluate((el, block) => el.scrollIntoView({ block }), edge);
      await trigger.click();
      const panel = page.getByRole('dialog', {
        name: 'attendance reminder permission details',
        exact: true,
      });
      const title = panel.getByTestId('discord-permission-details-title');
      const scroll = panel.getByTestId('discord-permission-details-scroll');
      await expect(title).toHaveText('attendance reminder permissions');
      await expectPaddedScroll(panel);
      const bounds = await panel.boundingBox();
      expect(bounds!.y).toBeGreaterThanOrEqual(15);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(485);
      expect(bounds!.x).toBeGreaterThanOrEqual(15);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(375);
      await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBe(0);
      await expectFullyInside(scroll.locator('h3').first(), scroll);
      await expectFullyInside(title, panel);
      const background = await page.evaluate(() => window.scrollY);
      await scroll.focus();
      await page.keyboard.press('End');
      await expectFullyInside(panel.locator('p').last(), scroll);
      await expectFullyInside(title, panel);
      await scroll.hover();
      await page.mouse.wheel(0, 600);
      expect(await page.evaluate(() => window.scrollY)).toBe(background);
      await page.keyboard.press('Home');
      await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBe(0);
      await expectFullyInside(scroll.locator('h3').first(), scroll);
      await page.keyboard.press('Escape');
      await expect(panel).toBeHidden();
      await expect(trigger).toBeFocused();
    });
  }

  test('a blocked announcement channel never turns the working signup channel red', async ({
    page,
  }) => {
    await channelChoices(page);
    const modal = await edit(page, data.fresh_event_pk);
    await modal.getByTestId('discord-discord_post_signups').check();
    await modal.getByTestId('discord-signup-channel-select').click();
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    await modal.getByTestId('discord-announcement-channel-select').click();
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    const signup = badge(modal, 'signup_post');
    const announcement = badge(modal, 'announcement');
    await expect(signup).toHaveText('Permissions verified');
    await expect(announcement).toHaveText('3 settings blocked');
    await announcement.click();
    const panel = page.getByRole('dialog', {
      name: 'Announcement channel permission details',
    });
    await expect(panel).toContainText(
      "Pre-day announcement won't post here — missing Embed Links.",
    );
    await expect(panel).toContainText(
      "Post event signup embed (announcement fallback) won't post here — missing Embed Links.",
    );
    await page.keyboard.press('Escape');
    await modal.getByTestId('discord-discord_confirm_attendance').uncheck();
    await expect(announcement).toHaveText('2 settings blocked');
    await expect(signup).toHaveText('Permissions verified');
    await modal.getByTestId('discord-announcement-channel-select').click();
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    await expect(signup).toHaveCount(0);
    await expect(announcement).toHaveText('Permissions verified');
    await expect(
      modal.getByTestId('discord-permission-shared-signup_post'),
    ).toHaveText('Permissions shown on Announcement channel.');
  });

  test('each channel badge covers only the settings that send there and scrolls details in a short viewport', async ({
    page,
  }) => {
    await channelChoices(page);
    const modal = await edit(page, data.fresh_event_pk);
    await page.getByTestId('discord-discord_post_signups').check();
    await page.getByTestId('discord-signup-channel-select').click();
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    const trigger = badge(modal, 'signup_post');
    await expect(trigger).toHaveText('2 settings blocked');
    await expect(badge(modal, 'signup_fallback')).toHaveCount(0);
    await expect(badge(modal, 'attendance_reminder')).toHaveCount(0);
    await expect(
      modal.getByTestId('discord-permission-shared-attendance_reminder'),
    ).toHaveText('Permissions shown on Signup channel.');
    const announcement = badge(modal, 'announcement');
    await expect(announcement).toHaveText('Permissions verified');
    await announcement.click();
    const announcementPanel = page.getByRole('dialog', {
      name: 'Announcement channel permission details',
    });
    await expect(announcementPanel).toContainText(
      'Post event signup embed (announcement fallback) can post here.',
    );
    await expect(announcementPanel).toContainText(
      'Pre-day announcement can post here.',
    );
    await expect(announcementPanel).not.toContainText('blocked');
    await page.keyboard.press('Escape');
    await expect(announcementPanel).toBeHidden();
    await expect(
      trigger.getByTestId('discord-permission-discord-icon'),
    ).toBeVisible();
    await expect(
      trigger.getByTestId('discord-permission-info-icon'),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 500 });
    await trigger.click();
    const panel = page.getByRole('dialog', {
      name: 'Signup channel permission details',
    });
    await expect(panel).toContainText(
      "Post event signup embed won't post here — missing Embed Links.",
    );
    await expect(panel).toContainText(
      "Post attendance reminder in Discord won't post here — missing Embed Links.",
    );
    await expect(
      panel.getByRole('heading', {
        name: 'Post event signup embed permissions',
      }),
    ).toHaveCount(1);
    await expect(
      panel.getByRole('heading', {
        name: 'Post attendance reminder in Discord permissions',
      }),
    ).toHaveCount(1);
    await expect(
      panel.getByTestId('discord-permission-details-signup_post'),
    ).toContainText('Status: Missing permissions');
    await expect(
      panel.getByTestId('discord-permission-details-attendance_reminder'),
    ).toContainText('Status: Missing permissions');
    const bounds = await panel.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.y).toBeGreaterThanOrEqual(15);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(485);
    const title = panel.getByTestId('discord-permission-details-title');
    await expect(title).toHaveText('Signup channel permissions');
    await expectPaddedScroll(panel);
    await expectFullyInside(panel, modal);
    const footer = modal.getByTestId('form-dialog-submit');
    await expectFullyInside(footer, modal);
    const scroll = panel.getByTestId('discord-permission-details-scroll');
    await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBe(0);
    await expectFullyInside(title, panel);
    await expectFullyInside(
      panel.getByRole('heading', { name: 'Blocked', exact: true }),
      scroll,
    );
    expect(
      await scroll.evaluate((el) => el.scrollHeight > el.clientHeight),
    ).toBe(true);
    const backgroundScroll = () =>
      modal.evaluate((el) => ({
        page: window.scrollY,
        viewports: Array.from(
          el.querySelectorAll('[data-radix-scroll-area-viewport]'),
        )
          .filter(
            (viewport) =>
              !viewport.closest(
                '[aria-label="Signup channel permission details"]',
              ),
          )
          .map((viewport) => viewport.scrollTop),
      }));
    const background = await backgroundScroll();
    await scroll.hover();
    await page.mouse.wheel(0, 350);
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(0);
    expect(await backgroundScroll()).toEqual(background);
    await expectFullyInside(title, panel);
    await scroll.focus();
    await page.keyboard.press('End');
    await expectFullyInside(panel.locator('p').last(), scroll);
    await expectFullyInside(title, panel);
    await page.mouse.wheel(0, 500);
    expect(await backgroundScroll()).toEqual(background);
    await page.keyboard.press('Home');
    await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBe(0);
    await expectFullyInside(
      panel.getByRole('heading', { name: 'Blocked', exact: true }),
      scroll,
    );
    const session = await page.context().newCDPSession(page);
    await session.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    const x = bounds!.x + bounds!.width / 2;
    const y = bounds!.y + bounds!.height - 20;
    const distance = Math.min(120, bounds!.height - 40);
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x, y }],
    });
    for (let step = 1; step <= 8; step++) {
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => resolve()),
          ),
      );
      await session.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x, y: y - (distance * step) / 8 }],
      });
    }
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchEnd',
      touchPoints: [],
    });
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(0);
    await expectFullyInside(title, panel);
    expect(await backgroundScroll()).toEqual(background);
    await session.send('Emulation.setTouchEmulationEnabled', {
      enabled: false,
    });
    await session.detach();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
