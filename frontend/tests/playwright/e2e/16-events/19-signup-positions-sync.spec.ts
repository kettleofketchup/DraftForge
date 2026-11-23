/**
 * Positions changed in the signup modal show up in Edit Profile's Dota tab
 * without a reload, even when the profile was already loaded before signup.
 */

import type { BrowserContext, Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  test,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken, postWithCsrf } from '../../fixtures/events';

// event_player_16: not used by other specs.
const PLAYER_PK = 5016;
const BASELINE_POSITIONS = {
  carry: 1,
  mid: 2,
  offlane: 4,
  soft_support: 5,
  hard_support: 3,
};

async function loginPlayer(context: BrowserContext): Promise<void> {
  const resp = await context.request.post(`${API_URL}/tests/login-as/`, {
    data: { user_pk: PLAYER_PK },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`Login player failed: ${resp.status()}`);
}

async function setPositions(context: BrowserContext): Promise<void> {
  const resp = await postWithCsrf(context, `${API_URL}/profile_update`, {
    positions: BASELINE_POSITIONS,
  });
  if (!resp.ok()) throw new Error(`profile_update failed: ${resp.status()}`);
}

async function pickRating(
  page: Page,
  role: 'carry' | 'mid',
  label: string,
): Promise<void> {
  await page.getByTestId(`position-choice-${role}`).click();
  await page.getByRole('option', { name: label, exact: true }).click();
}

/** Client-side navigation to the own profile, then open Edit Profile → Dota. */
async function openDotaTab(page: Page): Promise<void> {
  await page.getByTestId('user-avatar').first().click();
  await page.getByTestId('navbarProfileButton').click();
  await expect(page).toHaveURL(new RegExp(`/user/${PLAYER_PK}`));
  // The profile link sits in a menu label, so the menu stays open.
  await page.keyboard.press('Escape');
  await page.getByTestId('edit-user-btn').first().click();
  await page.getByTestId('edit-user-tab-dota').click();
  await expect(page.getByTestId('edit-user-dota-save')).toBeVisible();
}

async function expectDotaPositions(
  page: Page,
  carry: number,
  mid: number,
): Promise<void> {
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByTestId('position-choice-carry')).toContainText(
    new RegExp(`^${carry}: `),
  );
  await expect(dialog.getByTestId('position-choice-mid')).toContainText(
    new RegExp(`^${mid}: `),
  );
}

async function closeDialog(page: Page): Promise<void> {
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Cancel' })
    .click();
  await expect(page.getByRole('dialog')).toBeHidden();
}

test('positions edited in the signup modal reach Edit Profile without a reload', async ({
  context,
  page,
}) => {
  const eventsData = await getEventsTestData(context);

  await loginEventAdmin(context);
  const createResp = await postWithCsrf(
    context,
    `${API_URL}/events/?open_signups=true`,
    {
      organization: eventsData.orgPk,
      name: `Positions Sync ${Date.now()}`,
      description: 'Signup positions sync',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Positions Sync Tournament',
      tournament_league: eventsData.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: true,
      allow_active_mmr: true,
      allow_previous_rank: true,
      allow_battlecup_rating: true,
      timezone: 'America/New_York',
    },
  );
  expect(createResp.ok()).toBeTruthy();
  const eventId = ((await createResp.json()) as { id: number }).id;

  try {
    await loginPlayer(context);
    await setPositions(context);

    // Present an unset rank so the modal opens on every run; the signup
    // itself still goes to the real backend.
    await page.route(
      '**/api/organizations/*/my-dota-profile/',
      async (route) => {
        const response = await route.fetch();
        const body = (await response.json()) as Record<string, unknown>;
        await route.fulfill({
          response,
          json: {
            ...body,
            rank_status: 'never',
            rank_medal: null,
            battle_cup_tier: null,
            pos_1: false,
            pos_2: false,
            pos_3: false,
            pos_4: false,
            pos_5: false,
          },
        });
      },
    );

    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto(`/events/${eventId}`);
    await page.evaluate(() => {
      (window as unknown as { __noReload: boolean }).__noReload = true;
    });

    // Warm the Edit Profile query with the old positions.
    await openDotaTab(page);
    await expectDotaPositions(page, 1, 2);
    await closeDialog(page);
    await page.goBack();

    await page.getByTestId('event-signup-btn').click();
    const modal = page.getByTestId('event-signup-modal');
    await expect(modal).toBeVisible();
    const chip = modal.getByTestId('signup-prefilled-summary-positions');
    await expect(chip).toContainText('Carry · Mid');

    await modal.getByTestId('signup-rank-status-previous').click();
    await modal.getByTestId('signup-rank-medal').click();
    await page.getByRole('option', { name: 'Legend', exact: true }).click();
    await modal.getByTestId('signup-rank-star').click();
    await page.getByRole('option', { name: 'Star 1', exact: true }).click();

    await chip.click();
    await pickRating(page, 'carry', '2: Can play');
    await pickRating(page, 'mid', '1: Favorite');
    await modal.getByTestId('event-signup-submit-btn').click();
    await expect(modal).toHaveCount(0, { timeout: 10000 });

    await openDotaTab(page);
    await expectDotaPositions(page, 2, 1);
    await closeDialog(page);
    expect(
      await page.evaluate(
        () => (window as unknown as { __noReload?: boolean }).__noReload,
      ),
    ).toBe(true);
  } finally {
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await loginPlayer(context);
    await setPositions(context);
    await loginEventAdmin(context);
    await context.request.delete(`${API_URL}/events/${eventId}/`, {
      headers: { 'X-CSRFToken': await getCsrfToken(context) },
    });
  }
});
