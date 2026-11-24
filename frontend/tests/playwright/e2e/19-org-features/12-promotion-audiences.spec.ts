import type { Page, Request } from '@playwright/test';
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
type Row = {
  user_pk: number | null;
  discordId: string;
  signed_up: boolean;
  mmr: number | null;
};
type Ref = { pk: number | null; discord_id: string; mmr?: number | null };

const ROW = 'promo-candidate-row-';

function candidateResponse(
  page: Page,
  match: (params: URLSearchParams) => boolean,
) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'GET' &&
      url.pathname.endsWith('/candidates/') &&
      match(url.searchParams)
    );
  });
}

async function source(page: Page, value: Source): Promise<Row[]> {
  const response = candidateResponse(page, (p) => p.get('source') === value);
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
  const response = candidateResponse(
    page,
    (p) => p.get('source') === value && p.get('days') === String(count),
  );
  await page.getByTestId('promo-days').click();
  await page.getByTestId(`promo-days-${count}`).click();
  const result = await response;
  expect(result.status()).toBe(200);
  return (await result.json()).rows;
}

function rowId(ref: Ref): string {
  return ref.pk === null ? `discord-${ref.discord_id}` : String(ref.pk);
}

async function search(page: Page, term: string): Promise<void> {
  const response = candidateResponse(page, (p) => p.get('q') === term);
  await page.getByTestId('promo-candidate-search').fill(term);
  expect((await response).status()).toBe(200);
}

async function renderedIds(page: Page, only?: string[]): Promise<string[]> {
  return page
    .locator(`[data-testid^="${ROW}"]`)
    .evaluateAll(
      (elements, [prefix, ids]) =>
        elements
          .map((element) =>
            element.getAttribute('data-testid')!.replace(prefix as string, ''),
          )
          .filter((id) => !ids || (ids as string[]).includes(id)),
      [ROW, only ?? null] as const,
    );
}

async function visibleRows(page: Page, ids: string[]): Promise<void> {
  await expect(page.locator(`[data-testid^="${ROW}"]`)).toHaveCount(ids.length);
  await expect.poll(() => renderedIds(page)).toEqual(ids);
}

async function setMmr(
  page: Page,
  bound: 'min' | 'max',
  value: string,
  expected: { min: string | null; max: string | null },
): Promise<Row[]> {
  const response = candidateResponse(
    page,
    (p) =>
      p.get('min_mmr') === expected.min && p.get('max_mmr') === expected.max,
  );
  await page.getByTestId(`promo-${bound}-mmr`).fill(value);
  const result = await response;
  expect(result.status()).toBe(200);
  return (await result.json()).rows;
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
    await expect(page.getByTestId('promo-candidate-table')).toBeVisible();
  }

  function template() {
    return data.templates.find(
      (t) => t.org_pk === data.orgs.features.pk && t.name === 'First invite',
    )!;
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
        await expect(page.getByTestId(`${ROW}${rowId(refs[key])}`)).toHaveCount(
          0,
        );
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
          .poll(() => renderedIds(page, audienceIds))
          .toEqual(expected.map((key) => rowId(refs[key])));
        await expect(page.getByTestId('promo-active-filter-window')).toHaveText(
          `Last ${window} days`,
        );
        for (const key of ['old', 'signed', 'messaged', 'declined', 'bot']) {
          await expect(
            page.getByTestId(`${ROW}${rowId(refs[key])}`),
          ).toHaveCount(0);
        }
        await expect(
          page.getByTestId(`${ROW}${data.users.promoter.pk}`),
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
      await expect(
        page.getByTestId(`promo-candidate-badges-${rowId(refs.signed)}`),
      ).toHaveText('Signed up');
      await page.getByTestId('promo-hide-signed-up').click();
      await visibleRows(page, []);
      await search(page, 'Guild messaged');
      await page.getByTestId('promo-hide-messaged').click();
      await expect(page.getByTestId('promo-active-filter-messaged')).toHaveText(
        'Showing messaged',
      );
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
      await page.getByTestId('promo-filters-reset').click();
      await expect(page.getByTestId('promo-candidate-search')).toHaveValue('');
      await expect(page.getByTestId('promo-filters-reset')).toHaveCount(0);
    });
  }

  test('org MMR column, Unknown, and inclusive min/max filters run on the server', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    const refs = data.audiences!;
    const ids = ['fresh', 'week', 'month', 'quarter'].map((k) =>
      rowId(refs[k]),
    );
    const rows = await days(page, 'active', 90);
    const byId = new Map(rows.map((r) => [String(r.user_pk), r]));
    expect(byId.get(ids[0])?.mmr).toBe(4500);
    expect(byId.get(ids[1])?.mmr).toBeNull();
    await expect(page.getByTestId(`promo-candidate-mmr-${ids[0]}`)).toHaveText(
      '4,500',
    );
    await expect(page.getByTestId(`promo-candidate-mmr-${ids[1]}`)).toHaveText(
      'Unknown',
    );
    await expect(page.getByTestId(`promo-candidate-mmr-${ids[2]}`)).toHaveText(
      '3,000',
    );
    await expect(page.getByTestId('promo-mmr-help')).toContainText(
      'Dota 2 rating',
    );

    const atLeast = await setMmr(page, 'min', '3000', {
      min: '3000',
      max: null,
    });
    expect(atLeast.every((r) => r.mmr != null && r.mmr >= 3000)).toBe(true);
    await expect
      .poll(() => renderedIds(page, ids))
      .toEqual([ids[0], ids[2], ids[3]]);
    await expect(page.getByTestId('promo-mmr-unknown-hint')).toBeVisible();
    await expect(page.getByTestId('promo-active-filter-mmr')).toHaveText(
      'Dota 2 MMR ≥ 3000',
    );

    await setMmr(page, 'max', '4500', { min: '3000', max: '4500' });
    await expect.poll(() => renderedIds(page, ids)).toEqual([ids[0], ids[2]]);
    await expect(page.getByTestId('promo-active-filter-mmr')).toHaveText(
      'Dota 2 MMR 3000–4500',
    );

    await page.getByTestId('promo-max-mmr').fill('2000');
    await expect(page.getByTestId('promo-mmr-error')).toHaveText(
      'Max MMR must be at least the min MMR',
    );
    await expect.poll(() => renderedIds(page, ids)).toEqual([ids[0], ids[2]]);

    await page.getByTestId('promo-max-mmr').fill('');
    await setMmr(page, 'min', '9000', { min: '9000', max: null });
    await expect(page.getByTestId('promo-candidates-empty')).toContainText(
      'Clear the MMR filter',
    );

    await setMmr(page, 'min', '4000', { min: '4000', max: null });
    const discord = candidateResponse(
      page,
      (p) => p.get('source') === 'discord' && p.get('min_mmr') === '4000',
    );
    await page.getByTestId('promo-source-discord').click();
    const discordRows = (await (await discord).json()).rows as Row[];
    expect(discordRows.some((r) => r.user_pk === null)).toBe(false);
    await expect(page.getByTestId(`${ROW}${rowId(refs.unlinked)}`)).toHaveCount(
      0,
    );
    await expect(page.getByTestId(`${ROW}${rowId(refs.fresh)}`)).toBeVisible();

    await page.getByTestId('promo-filters-reset').click();
    await expect(
      page.getByTestId(`${ROW}${rowId(refs.unlinked)}`),
    ).toBeVisible();
  });

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
      // The dialog renders its default template as soon as it opens.
      const rendering = page.waitForResponse(
        (r) =>
          r.url().endsWith(`${base}/render/`) &&
          r.request().method() === 'POST',
      );
      await page.getByTestId(`promo-candidate-message-${rowId(ref)}`).click();
      const resolvedResponse = await resolving;
      expect(resolvedResponse.status()).toBe(200);
      const resolved = (await resolvedResponse.json()) as Row;
      expect(resolved.user_pk).toBeGreaterThan(0);
      const dialog = page.getByTestId('promo-message-dialog');
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('heading')).toHaveText(
        /^Message \S+ unlinked$/,
      );
      await expect(page.getByTestId('promo-dialog-description')).toContainText(
        'MMR Unknown',
      );
      await page.getByTestId('promo-template-select').click();
      await page.getByTestId(`promo-template-option-${template().pk}`).click();
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

  test('listing and filtering never create accounts; a late resolution after switching audience opens nothing', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    const ref = data.audiences!.unlinked;
    const base = `/organizations/${data.orgs.features.pk}/promotion/events/${data.events.upcoming.pk}`;
    await open(page);
    await source(page, 'discord');
    await search(page, 'Guild unlinked');
    await visibleRows(page, [rowId(ref)]);
    const listed = await orgFeaturesApi<{ rows: Row[] }>(
      context,
      'GET',
      `${base}/candidates/?source=discord&days=90&q=handle_unlinked`,
    );
    expect(listed.rows.map((r) => r.user_pk)).toEqual([null]);

    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(`**${base}/candidates/discord/`, async (route) => {
      await gate;
      await route.continue();
    });
    const resolving = page.waitForResponse(
      (r) =>
        r.url().endsWith(`${base}/candidates/discord/`) &&
        r.request().method() === 'POST',
    );
    await page.getByTestId(`promo-candidate-message-${rowId(ref)}`).click();
    await expect(
      page.getByTestId(`promo-candidate-message-${rowId(ref)}`),
    ).toBeDisabled();
    await source(page, 'active');
    release();
    expect((await resolving).status()).toBe(200);
    await page.waitForTimeout(300);
    await expect(page.getByTestId('promo-message-dialog')).toHaveCount(0);
    await page.unroute(`**${base}/candidates/discord/`);
  });

  test('Mark as sent: cancel records nothing, confirm records, undo reverts, server errors stay in the dialog', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    const fresh = data.audiences!.fresh;
    const base = `/organizations/${data.orgs.features.pk}/promotion/events/${data.events.upcoming.pk}`;
    const posts: Request[] = [];
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().endsWith(`${base}/sends/`))
        posts.push(r);
    });

    await page.getByTestId(`promo-candidate-record-${fresh.pk}`).click();
    const dialog = page.getByTestId('promo-message-dialog');
    await expect(dialog.getByRole('heading')).toHaveText(
      /^Record a message to \S+ fresh$/,
    );
    await expect(page.getByTestId('promo-record-note')).toContainText(
      'Nothing is sent from DraftForge',
    );
    await expect(page.getByTestId('promo-dialog-description')).toContainText(
      'Dota 2 MMR 4,500',
    );
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template().pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toHaveValue(
      /^Hey Guild fresh!/,
    );
    await page.getByTestId('promo-message-text').fill('   ');
    await expect(page.getByTestId('promo-mark-sent-btn')).toBeDisabled();
    await page.getByTestId('promo-dialog-close').click();
    await expect(dialog).toHaveCount(0);
    expect(posts).toHaveLength(0);
    await expect(
      page.getByTestId(`promo-last-messaged-${fresh.pk}`),
    ).toHaveCount(0);

    await page.route(`**${base}/sends/`, (route) =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ recipient_id: ['not in this audience'] }),
      }),
    );
    await page.getByTestId(`promo-candidate-record-${fresh.pk}`).click();
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template().pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toHaveValue(
      /^Hey Guild fresh!/,
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    await expect(page.getByText('not in this audience')).toBeVisible();
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId('promo-sent-banner')).toHaveCount(0);
    await page.unroute(`**${base}/sends/`);

    const sending = page.waitForResponse(
      (r) =>
        r.url().endsWith(`${base}/sends/`) && r.request().method() === 'POST',
    );
    await expect(page.getByTestId('promo-mark-sent-btn')).toHaveText(
      'Record as sent',
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    const sent = await sending;
    expect(sent.status()).toBe(201);
    const send = (await sent.json()) as { id: number };
    await expect(page.getByTestId('promo-sent-banner')).toBeVisible();
    await expect(page.getByTestId('promo-mark-sent-btn')).toBeDisabled();

    const undoing = page.waitForResponse(
      (r) =>
        r.url().includes(`/promotion/sends/${send.id}/`) &&
        r.request().method() === 'DELETE',
    );
    await page.getByTestId(`promo-undo-${send.id}`).click();
    expect((await undoing).status()).toBe(204);
    await expect(page.getByTestId('promo-sent-banner')).toHaveCount(0);
    await page.getByTestId('promo-dialog-close').click();
    await page.getByTestId('promo-hide-messaged').click();
    await expect(page.getByTestId(`${ROW}${fresh.pk}`)).toBeVisible();
    await expect(
      page.getByTestId(`promo-last-messaged-${fresh.pk}`),
    ).toHaveCount(0);
  });

  test('closing the dialog and switching audience clears the recipient', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    await page
      .getByTestId(`promo-candidate-message-${data.audiences!.fresh.pk}`)
      .click();
    await expect(page.getByTestId('promo-message-text')).toBeVisible();
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template().pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toHaveValue(
      /^Hey Guild fresh!/,
    );
    const sending = page.waitForResponse(
      (r) => r.url().endsWith('/sends/') && r.request().method() === 'POST',
    );
    await page.getByTestId('promo-mark-sent-btn').click();
    expect((await sending).status()).toBe(201);
    await expect(page.getByTestId('promo-sent-banner')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('promo-message-dialog')).toHaveCount(0);
    await source(page, 'discord');
    await expect(page.getByTestId('promo-message-text')).toHaveCount(0);
    await page.getByTestId('promo-source-recent').click();
    await expect(page.getByTestId('promo-message-dialog')).toHaveCount(0);
  });

  test('phone: filters stack, row actions use the menu, dialog fits the screen', async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginOrgFeatures(context, 'promoter');
    await open(page);
    await source(page, 'active');
    const fresh = data.audiences!.fresh;
    await setMmr(page, 'min', '4000', { min: '4000', max: null });
    await expect(page.getByTestId(`${ROW}${fresh.pk}`)).toBeVisible();
    await expect(
      page.getByTestId(`promo-candidate-mmr-stacked-${fresh.pk}`),
    ).toHaveText('MMR 4,500');
    await expect(
      page.getByTestId(`promo-candidate-mmr-${fresh.pk}`),
    ).toBeHidden();
    await expect(
      page.getByTestId(`promo-candidate-message-${fresh.pk}`),
    ).toHaveCount(0);
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(390);

    await page.getByTestId(`promo-candidate-actions-${fresh.pk}`).click();
    await page.getByTestId(`promo-candidate-message-${fresh.pk}`).click();
    const dialog = page.getByTestId('promo-message-dialog');
    await expect(dialog).toBeVisible();
    const box = (await dialog.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.height).toBeLessThanOrEqual(844);
    await page.getByTestId('promo-template-select').click();
    await page.getByTestId(`promo-template-option-${template().pk}`).click();
    await expect(page.getByTestId('promo-message-text')).toHaveValue(
      /^Hey Guild fresh!/,
    );
    await page.getByTestId('promo-mark-sent-btn').scrollIntoViewIfNeeded();
    await expect(page.getByTestId('promo-mark-sent-btn')).toBeInViewport();
    await page.getByTestId('promo-dialog-close').click();
    await expect(dialog).toHaveCount(0);
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
          `${API_URL}${base}/candidates/?source=${audience}&days=90&min_mmr=1`,
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
