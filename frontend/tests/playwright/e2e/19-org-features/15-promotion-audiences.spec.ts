import type { Page } from '@playwright/test';
import {
  expect,
  loginOrgFeatures,
  orgFeaturesApi,
  postWithCsrf,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

type Source = 'active' | 'discord';
type Row = { user_pk: number | null; discordId: string; signed_up: boolean };

function candidateResponse(page: Page, source: Source, days?: number) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'GET' &&
      url.pathname.endsWith('/candidates/') &&
      url.searchParams.get('source') === source &&
      (days === undefined || url.searchParams.get('days') === String(days))
    );
  });
}

async function source(page: Page, value: Source): Promise<Row[]> {
  const response = candidateResponse(page, value);
  await page.getByTestId(`promo-source-${value}`).click();
  const result = await response;
  expect(result.status()).toBe(200);
  await expect(page.getByTestId(`promo-source-${value}`)).toHaveAttribute(
    'data-state',
    'on',
  );
  return (await result.json()).rows;
}

async function days(page: Page, value: Source, count: number): Promise<Row[]> {
  const response = candidateResponse(page, value, count);
  await page.getByTestId('promo-days').click();
  await page.getByTestId(`promo-days-${count}`).click();
  const result = await response;
  expect(result.status()).toBe(200);
  return (await result.json()).rows;
}

function rowId(ref: { pk: number | null; discord_id: string }): string {
  return ref.pk === null ? `discord-${ref.discord_id}` : String(ref.pk);
}

async function search(page: Page, term: string): Promise<void> {
  const response = page.waitForResponse((result) => {
    const url = new URL(result.url());
    return (
      result.request().method() === 'GET' &&
      url.pathname.endsWith('/candidates/') &&
      url.searchParams.get('q') === term
    );
  });
  await page.getByTestId('promo-search').fill(term);
  expect((await response).status()).toBe(200);
}

async function visibleRows(page: Page, ids: string[]): Promise<void> {
  await expect(page.locator('[data-testid^="promo-select-"]')).toHaveCount(
    ids.length,
  );
  await expect
    .poll(async () =>
      page
        .locator('[data-testid^="promo-select-"]')
        .evaluateAll((elements) =>
          elements.map((element) =>
            element.getAttribute('data-testid')!.replace('promo-select-', ''),
          ),
        ),
    )
    .toEqual(ids);
}

test.describe('Promotion candidate audiences @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request, { audiences: true });
  });

  test.afterAll(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  async function open(page: Page): Promise<void> {
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=promotion&event=${data.events.upcoming.pk}`,
    );
    await expect(page.getByTestId('promo-source-recent')).toHaveAttribute(
      'data-state',
      'on',
    );
    await expect(page.getByTestId('promo-pool-n')).toBeVisible();
  }

  for (const audience of ['active', 'discord'] as const) {
    test(`${audience}: 7/14/30/90 day windows, newest first, active-only membership`, async ({
      page,
      context,
    }) => {
      await loginOrgFeatures(context, 'promoter');
      await open(page);
      const refs = data.audiences!;
      for (const key of ['fresh', 'week', 'month', 'quarter']) {
        await expect(
          page.getByTestId(`promo-select-${rowId(refs[key])}`),
        ).toHaveCount(0);
      }
      const initial = await source(page, audience);
      await expect(page.getByTestId('promo-pool-n')).toHaveCount(0);
      for (const [window, keys] of [
        [30, ['fresh', 'week', 'month']],
        [7, ['fresh']],
        [14, ['fresh', 'week']],
        [90, ['fresh', 'week', 'month', 'quarter']],
      ] as const) {
        const response =
          window === 30 ? initial : await days(page, audience, window);
        const expected =
          audience === 'discord' ? ['unlinked', ...keys] : [...keys];
        const audienceRows = response.filter((row) =>
          Object.values(refs).some((ref) => ref.discord_id === row.discordId),
        );
        expect(audienceRows.map((row) => row.discordId)).toEqual(
          expected.map((key) => refs[key].discord_id),
        );
        const audienceIds = Object.values(refs).map(rowId);
        await expect
          .poll(async () =>
            page
              .locator('[data-testid^="promo-select-"]')
              .evaluateAll(
                (elements, ids) =>
                  elements
                    .map((element) =>
                      element
                        .getAttribute('data-testid')!
                        .replace('promo-select-', ''),
                    )
                    .filter((id) => ids.includes(id)),
                audienceIds,
              ),
          )
          .toEqual(expected.map((key) => rowId(refs[key])));
        for (const key of ['old', 'signed', 'messaged', 'declined', 'bot']) {
          await expect(
            page.getByTestId(`promo-select-${rowId(refs[key])}`),
          ).toHaveCount(0);
        }
        await expect(
          page.getByTestId(`promo-select-${data.users.promoter.pk}`),
        ).toHaveCount(0);
      }
    });

    test(`${audience}: guild/global/handle search and hide signed-up/messaged`, async ({
      page,
      context,
    }) => {
      await loginOrgFeatures(context, 'staff');
      await open(page);
      await source(page, audience);
      const refs = data.audiences!;
      for (const term of ['Guild fresh', 'Global fresh', 'handle_fresh']) {
        await search(page, term);
        await visibleRows(page, [rowId(refs.fresh)]);
      }
      if (audience === 'discord') {
        for (const term of [
          'Guild unlinked',
          'Global unlinked',
          'handle_unlinked',
        ]) {
          await search(page, term);
          await visibleRows(page, [rowId(refs.unlinked)]);
        }
      }
      await search(page, 'Guild signed');
      await visibleRows(page, []);
      await page.getByTestId('promo-hide-signed-up').click();
      await visibleRows(page, [rowId(refs.signed)]);
      await page.getByTestId('promo-hide-signed-up').click();
      await visibleRows(page, []);
      await search(page, 'Guild messaged');
      await page.getByTestId('promo-hide-messaged').click();
      await visibleRows(page, [rowId(refs.messaged)]);
      await expect(
        page.getByTestId(`promo-last-messaged-${refs.messaged.pk}`),
      ).toBeVisible();
      await page.getByTestId('promo-hide-messaged').click();
      await visibleRows(page, []);
      await page.getByTestId('promo-hide-signed-up').click();
      await page.getByTestId('promo-hide-messaged').click();
      await search(page, 'Guild declined');
      await visibleRows(page, []);
    });
  }

  for (const role of ['promoter', 'staff'] as const) {
    test(`${role}: new Discord member resolves once, renders/sends through API, survives reload without duplicates`, async ({
      page,
      context,
    }) => {
      await loginOrgFeatures(context, role);
      await open(page);
      await source(page, 'discord');
      const ref = data.audiences!.unlinked;
      const base = `/organizations/${data.orgs.features.pk}/promotion/events/${data.events.upcoming.pk}`;
      const resolving = page.waitForResponse(
        (r) =>
          r.url().endsWith(`${base}/candidates/discord/`) &&
          r.request().method() === 'POST',
      );
      await page.getByTestId(`promo-select-${rowId(ref)}`).click();
      const resolvedResponse = await resolving;
      expect(resolvedResponse.status()).toBe(200);
      const resolved = (await resolvedResponse.json()) as Row;
      expect(resolved.user_pk).toBeGreaterThan(0);
      const template = data.templates.find(
        (t) => t.org_pk === data.orgs.features.pk && t.name === 'First invite',
      )!;
      const rendering = page.waitForResponse(
        (r) =>
          r.url().endsWith(`${base}/render/`) &&
          r.request().method() === 'POST',
      );
      await page.getByTestId('promo-template-select').click();
      await page.getByTestId(`promo-template-option-${template.pk}`).click();
      expect((await rendering).status()).toBe(200);
      await expect(page.getByTestId('promo-message-text')).toHaveValue(
        /^Hey Global unlinked!/,
      );
      const sending = page.waitForResponse(
        (r) =>
          r.url().endsWith(`${base}/sends/`) && r.request().method() === 'POST',
      );
      await page.getByTestId('promo-mark-sent-btn').click();
      expect((await sending).status()).toBe(201);
      await expect(page.getByTestId('promo-sent-banner')).toBeVisible();
      await page.reload();
      await source(page, 'discord');
      await search(page, 'Guild unlinked');
      await visibleRows(page, []);
      await page.getByTestId('promo-hide-messaged').click();
      await visibleRows(page, [String(resolved.user_pk)]);
      const again = await orgFeaturesApi<Row>(
        context,
        'POST',
        `${base}/candidates/discord/`,
        { discord_id: ref.discord_id },
      );
      expect(again.user_pk).toBe(resolved.user_pk);
      await page.reload();
      await source(page, 'discord');
      await page.getByTestId('promo-hide-messaged').click();
      await search(page, 'Guild unlinked');
      await visibleRows(page, [String(resolved.user_pk)]);
    });
  }

  test('switching audience clears the previously selected recipient', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    await page.getByTestId(`promo-select-${data.audiences!.fresh.pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toBeVisible();
    const template = data.templates.find(
      (t) => t.org_pk === data.orgs.features.pk && t.name === 'First invite',
    )!;
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template.pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toHaveValue(
      /^Hey Guild fresh!/,
    );
    const sending = page.waitForResponse(
      (r) => r.url().endsWith('/sends/') && r.request().method() === 'POST',
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    expect((await sending).status()).toBe(201);
    await expect(page.getByTestId('promo-sent-banner')).toBeVisible();
    await source(page, 'discord');
    await expect(page.getByTestId('promo-pick-player')).toBeVisible();
    await expect(page.getByTestId('promo-message-text')).toHaveCount(0);
    await page.getByTestId('promo-source-recent').click();
    await expect(page.getByTestId('promo-pick-player')).toBeVisible();
  });

  for (const role of ['member', 'outsider'] as const) {
    test(`${role} cannot list or resolve audience candidates`, async ({
      context,
      page,
    }) => {
      await loginOrgFeatures(context, role);
      const base = `/organizations/${data.orgs.features.pk}/promotion/events/${data.events.upcoming.pk}`;
      for (const audience of ['active', 'discord']) {
        const response = await context.request.get(
          `${API_URL}${base}/candidates/?source=${audience}&days=90`,
        );
        expect(response.status()).toBe(403);
      }
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}?tab=promotion`,
      );
      await expect(page.getByTestId('promo-candidate-list')).toHaveCount(0);
      await expect(page.getByTestId('promo-source')).toHaveCount(0);
      const denied = await postWithCsrf(
        context,
        `${API_URL}${base}/candidates/discord/`,
        {
          discord_id: data.audiences!.unlinked.discord_id,
        },
      );
      expect(denied.status()).toBe(403);
      expect(await denied.text()).not.toContain('CSRF');
    });
  }
});
