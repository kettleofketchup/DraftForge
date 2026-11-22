import type { Locator, Page } from '@playwright/test';

import { findOverflow } from '../../../../scripts/find-overflow';
import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

const REVIEW_ROW = /^leadership-review-row-(\d+)$/;
const SCORE_4 = /^leadership-review-(.+)-4$/;

function radio(page: Page, key: string, score: number): Locator {
  return page
    .getByTestId(`leadership-review-${key}-${score}`)
    .getByRole('radio');
}

async function traitKeys(dialog: Locator): Promise<string[]> {
  const ids = await dialog
    .locator('[data-testid^="leadership-review-"][data-testid$="-4"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('data-testid')));
  const keys = ids.map((id) => SCORE_4.exec(id ?? '')?.[1] ?? '');
  expect(keys.length).toBeGreaterThan(0);
  expect(keys).not.toContain('');
  return keys;
}

async function firstReviewPk(table: Locator): Promise<number> {
  const id = await table
    .locator('[data-testid^="leadership-review-row-"]')
    .first()
    .getAttribute('data-testid');
  const pk = Number(REVIEW_ROW.exec(id ?? '')?.[1]);
  expect(pk).toBeGreaterThan(0);
  return pk;
}

async function voidReview(
  page: Page,
  pk: number,
  reason: string,
): Promise<void> {
  await page.getByTestId(`leadership-void-${pk}`).click();
  const dialog = page.getByTestId('leadership-void-dialog');
  await expect(dialog).toBeVisible();
  await page.getByTestId('leadership-void-reason').fill(reason);
  const voided = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes(`/leadership/reviews/${pk}/void/`),
  );
  await page.getByTestId('leadership-void-confirm').click();
  expect((await voided).ok()).toBe(true);
  await expect(dialog).toHaveCount(0);
}

async function restoreReview(page: Page, pk: number): Promise<void> {
  const restored = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes(`/leadership/reviews/${pk}/unvoid/`),
  );
  await page.getByTestId(`leadership-unvoid-${pk}`).click();
  expect((await restored).ok()).toBe(true);
}

async function expectNoOverflow(page: Page, where: string): Promise<void> {
  for (const width of [390, 700]) {
    await page.setViewportSize({ width, height: 844 });
    await page.waitForTimeout(100);
    const offenders = await page.evaluate(findOverflow);
    expect(
      offenders,
      `${where} at ${width}px\n${JSON.stringify(offenders, null, 2)}`,
    ).toEqual([]);
  }
}

test.describe('Org features: leadership @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('captain sees their own released rating @cicd', async ({
    page,
    context,
  }) => {
    const { event_pk } = data.leadership;
    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=leadership`,
    );

    const tab = page.getByTestId('leadership-tab');
    await expect(tab).toBeVisible();
    await expect(page.getByTestId('leadership-self-only')).toBeVisible();
    const member = page.getByTestId('leadership-member');
    await expect(member).toBeVisible();
    await expect(page.getByTestId('leadership-member-own-note')).toBeVisible();
    await expect(page.getByTestId('leadership-member-rating')).toHaveText(/\d/);

    const event = page.getByTestId(`leadership-member-event-${event_pk}`);
    await expect(event).toBeVisible();
    await expect(event).toContainText('3 reviews');
    await expect(event).toContainText('Communication');
    await expect(
      page.getByTestId(`leadership-member-event-${event_pk}-unreleased`),
    ).toHaveCount(0);

    // The raters (players 1-3, nicknamed "Features Player N", player 1 "Ashveil") stay hidden.
    for (const scope of [tab, member]) {
      await expect(scope).not.toContainText(/of_player_[123]\b/);
      await expect(scope).not.toContainText(/Features Player [123]\b/);
      await expect(scope).not.toContainText('Ashveil');
    }
    await expect(
      page.locator('[data-testid^="leadership-review-row-"]'),
    ).toHaveCount(0);
    await expect(
      page.locator('[data-testid^="leadership-moderation"]'),
    ).toHaveCount(0);

    await expect(page.getByTestId('leadership-period-select')).toHaveCount(0);
    await page.getByTestId('standing-metric-leadership').click();
    const switched = page.waitForResponse(
      (r) =>
        r.url().includes('/standing/leadership/leaderboard/') &&
        r.url().includes('metric=points'),
    );
    await page.getByTestId('standing-metric-leadership-points').click();
    expect((await switched).ok()).toBe(true);
    await expect(page.getByTestId('leadership-period-select')).toBeVisible();
  });

  test('teammate rates their captain from the event page @cicd', async ({
    page,
    context,
  }) => {
    const { event_pk, open_captain_org_user_pk, pending_rater_role } =
      data.leadership;
    const id = `${event_pk}-${open_captain_org_user_pk}`;
    await loginOrgFeatures(context, pending_rater_role);
    await visitAndWaitForHydration(page, `/events/${event_pk}`);

    const banner = page.getByTestId('event-leadership');
    await expect(page.getByTestId(`event-leadership-item-${id}`)).toBeVisible();
    await expect(page.getByTestId('event-leadership-count')).toContainText('1');
    await page.getByTestId(`event-leadership-open-${id}`).click();

    const dialog = page.getByTestId('leadership-review-dialog');
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId('leadership-review-countdown')).toBeVisible();
    const keys = await traitKeys(dialog);

    // Keyboard: the first trait moves 3 -> 4 with an arrow key. Radix moves focus a
    // tick after keydown and checks only while the key is held, so hold it.
    await page.getByTestId(`leadership-review-${keys[0]}-3`).click();
    await radio(page, keys[0], 3).focus();
    await page.keyboard.down('ArrowRight');
    await expect(radio(page, keys[0], 4)).toBeFocused();
    await page.keyboard.up('ArrowRight');
    await expect(radio(page, keys[0], 4)).toHaveAttribute(
      'data-state',
      'checked',
    );
    for (const key of keys.slice(1)) {
      await page.getByTestId(`leadership-review-${key}-4`).click();
    }

    const submitted = page.waitForResponse(
      (r) =>
        r.request().method() === 'PUT' &&
        r
          .url()
          .includes(
            `/leadership/events/${event_pk}/captains/${open_captain_org_user_pk}/review/`,
          ),
    );
    await page.getByTestId('leadership-review-submit').click();
    const body = (await submitted).request().postDataJSON() as {
      scores: Record<string, number>;
    };
    expect(body.scores).toEqual(Object.fromEntries(keys.map((k) => [k, 4])));
    await expect(dialog).toHaveCount(0);
    await expect(banner).toHaveCount(0);

    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=leadership`,
    );
    await expect(page.getByTestId(`leadership-pending-badge-${id}`)).toHaveText(
      'Submitted',
    );
    const open = page.getByTestId(`leadership-pending-open-${id}`);
    await expect(open).toHaveText('Edit');
    await expect(page.getByTestId('leadership-pending-count')).toContainText(
      '0',
    );

    await open.click();
    await expect(dialog).toBeVisible();
    await expect(radio(page, keys[0], 4)).toHaveAttribute(
      'data-state',
      'checked',
    );
    await page.getByTestId(`leadership-review-${keys[0]}-5`).click();
    const submit = page.getByTestId('leadership-review-submit');
    await expect(submit).toHaveText('Update');
    const updated = page.waitForResponse(
      (r) =>
        r.request().method() === 'PUT' &&
        r.url().includes(`/leadership/events/${event_pk}/captains/`),
    );
    await submit.click();
    expect((await updated).ok()).toBe(true);
    await expect(dialog).toHaveCount(0);

    await open.click();
    await expect(radio(page, keys[0], 5)).toHaveAttribute(
      'data-state',
      'checked',
    );
    const withdrawn = page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes(`/leadership/events/${event_pk}/captains/`),
    );
    await page.getByTestId('leadership-review-withdraw').click();
    expect((await withdrawn).ok()).toBe(true);
    await expect(dialog).toHaveCount(0);
    await expect(open).toHaveText('Rate');
    await expect(page.getByTestId(`leadership-pending-badge-${id}`)).toHaveText(
      'Withdrawn',
    );
    await expect(page.getByTestId('leadership-pending-count')).toContainText(
      '1',
    );
  });

  test('admin voids and restores a review @cicd', async ({ page, context }) => {
    const { event_pk, released_captain_org_user_pk } = data.leadership;
    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(page, `/events/${event_pk}`);

    await expect(page.getByTestId('leadership-moderation')).toBeVisible();
    const captain = page.getByTestId(
      `leadership-moderation-${released_captain_org_user_pk}`,
    );
    await expect(captain).toBeVisible();
    await expect(
      captain.locator('[data-testid^="leadership-review-row-"]'),
    ).toHaveCount(3);
    const pk = await firstReviewPk(captain);
    await expect(page.getByTestId(`leadership-status-${pk}`)).toHaveText(
      'Live',
    );

    await voidReview(page, pk, 'Spam');
    await expect(page.getByTestId(`leadership-status-${pk}`)).toHaveText(
      'Voided by staff',
    );
    await expect(page.getByTestId(`leadership-void-reason-${pk}`)).toHaveText(
      'Spam',
    );

    await restoreReview(page, pk);
    await expect(page.getByTestId(`leadership-status-${pk}`)).toHaveText(
      'Live',
    );
    await expect(page.getByTestId(`leadership-void-reason-${pk}`)).toHaveCount(
      0,
    );
    await expect(page.getByTestId(`leadership-void-${pk}`)).toBeVisible();

    // Org staff who is not an admin cannot moderate, and the backend refuses
    // other captains on a private board.
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    const memberCalls: { url: string; status: number }[] = [];
    page.on('response', (r) => {
      if (r.url().includes('/leadership/members/'))
        memberCalls.push({ url: r.url(), status: r.status() });
    });

    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(page, `/events/${event_pk}`);
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.getByTestId('leadership-moderation')).toHaveCount(0);

    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=leadership`,
    );
    const row = page.getByTestId(
      `leadership-row-${released_captain_org_user_pk}`,
    );
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.getByTestId('leadership-member-forbidden')).toHaveText(
      "Only org admins can see other captains' details.",
    );
    const refused = memberCalls.filter((c) =>
      c.url.includes(`/members/${released_captain_org_user_pk}/`),
    );
    expect(refused.length).toBeGreaterThan(0);
    expect(refused.every((c) => c.status === 403)).toBe(true);
    await expect(page.getByTestId('leadership-tab')).toBeVisible();
    await expect(page.getByText('An unexpected error occurred')).toHaveCount(0);
    expect(pageErrors).toEqual([]);
  });

  test('admin edits leadership settings and traits @cicd', async ({
    page,
    context,
  }) => {
    const pk = data.orgs.features.pk;
    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=leadership`,
    );
    const modal = page.getByTestId('org-settings-modal');
    await expect(modal).toBeVisible();
    await expect(page.getByTestId('org-settings-leadership')).toBeVisible();

    const windowHours = page.getByTestId(
      'leadership-setting-review_window_hours',
    );
    await expect(windowHours).toBeVisible();
    await windowHours.fill('48');
    await page.getByTestId('leadership-setting-points-captained').fill('7');
    await page.getByTestId('leadership-trait-new-label').fill('Shot calling');
    await page.getByTestId('leadership-trait-add').click();

    const patched = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/organizations/${pk}/leadership/settings/`),
    );
    const put = page.waitForResponse(
      (r) =>
        r.request().method() === 'PUT' &&
        r.url().includes(`/organizations/${pk}/leadership/traits/`),
    );
    await page.getByTestId('org-settings-save').click();
    expect((await patched).status()).toBe(200);
    expect((await put).status()).toBe(200);
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);

    // Without a reload, the metric picker already lists the new trait.
    await page.keyboard.press('Escape');
    await expect(modal).toHaveCount(0);
    await page.getByTestId(`org-tab-leadership`).click();
    await expect(page.getByTestId('leadership-tab')).toBeVisible();
    await page.getByTestId('standing-metric-leadership').click();
    await expect(
      page.getByRole('option', { name: 'Shot calling' }),
    ).toBeVisible();
    await page.keyboard.press('Escape');

    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=leadership`,
    );
    await expect(modal).toBeVisible();
    await expect(
      page.getByTestId('leadership-setting-review_window_hours'),
    ).toHaveValue('48');
    await expect(
      page.getByTestId('leadership-setting-points-captained'),
    ).toHaveValue('7');
    const labels = page.locator(
      '[data-testid^="leadership-trait-"][data-testid$="-label"]',
    );
    await expect(labels.first()).toBeVisible();
    expect(
      await labels.evaluateAll((els) =>
        els.map((el) => (el as HTMLInputElement).value),
      ),
    ).toEqual(expect.arrayContaining(['Communication', 'Shot calling']));

    const active = page.getByTestId('leadership-trait-communication-active');
    await expect(active).toBeChecked();
    await page.getByTestId('leadership-trait-communication-delete').click();
    const deleted = page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes(`/leadership/traits/communication/`),
    );
    await page.getByTestId('leadership-trait-delete-confirm').click();
    expect((await deleted).status()).toBe(409);
    await expect(
      page.getByTestId('leadership-trait-communication-error'),
    ).toHaveText('This trait has scores. Deactivate it instead.');
    await expect(active).not.toBeChecked();
    await expect(
      page.getByTestId('leadership-trait-communication'),
    ).toBeVisible();
  });

  test('leadership screens do not overflow at 390px @cicd', async ({
    page,
    context,
  }) => {
    const {
      event_pk,
      open_captain_org_user_pk,
      released_captain_org_user_pk,
      pending_rater_role,
    } = data.leadership;
    await page.setViewportSize({ width: 390, height: 844 });

    await loginOrgFeatures(context, pending_rater_role);
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=leadership`,
    );
    await expect(page.getByTestId('leadership-tab')).toBeVisible();
    await page
      .getByTestId(
        `leadership-pending-open-${event_pk}-${open_captain_org_user_pk}`,
      )
      .click();
    await expect(page.getByTestId('leadership-review-dialog')).toBeVisible();
    await expectNoOverflow(page, 'review dialog');

    await page.setViewportSize({ width: 390, height: 844 });
    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(page, `/events/${event_pk}`);
    const captain = page.getByTestId(
      `leadership-moderation-${released_captain_org_user_pk}`,
    );
    await expect(captain).toBeVisible();
    const pk = await firstReviewPk(captain);
    const reason = [
      'x'.repeat(60),
      ...Array.from({ length: 40 }, (_, i) => `word${i}`),
    ]
      .join(' ')
      .padEnd(300, ' filler')
      .slice(0, 300);
    expect(reason).toHaveLength(300);
    await voidReview(page, pk, reason);
    await expect(
      page.getByTestId(`leadership-void-reason-${pk}`),
    ).toBeVisible();
    await expectNoOverflow(page, 'moderation table');

    await restoreReview(page, pk);
    await expect(page.getByTestId(`leadership-void-reason-${pk}`)).toHaveCount(
      0,
    );
  });
});
