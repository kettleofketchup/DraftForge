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
      'Missing permissions',
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
      'Missing permissions',
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
    await expect(badge(reopened, 'attendance_reminder')).toHaveText(
      'Permissions verified',
    );
    await badge(reopened, 'attendance_reminder').click();
    await expect(
      page.getByTestId('discord-permission-details-attendance_reminder'),
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
});
