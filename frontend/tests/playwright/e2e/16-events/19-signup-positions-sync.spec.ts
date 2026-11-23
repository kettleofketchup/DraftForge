/**
 * Positions changed in the signup modal show up in the next signup modal
 * without a reload.
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

test('positions edited in the signup modal reach the next signup without a reload', async ({
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

    await page.goto(`/events/${eventId}`);
    let reloaded = false;
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame()) reloaded = true;
    });

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

    await page.getByTestId('event-cancel-rsvp-btn').click();
    await page
      .getByRole('alertdialog')
      .getByRole('button', { name: 'Cancel RSVP' })
      .click();
    await page.getByTestId('event-signup-btn').click();
    await expect(modal).toBeVisible();
    await expect(
      modal.getByTestId('signup-prefilled-summary-positions'),
    ).toContainText('Mid · Carry');
    expect(reloaded).toBe(false);
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
