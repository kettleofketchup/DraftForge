/**
 * Captain takeover from an eliminated team.
 *
 * Uses the `captain_takeover` tournament (the team management fixture under its
 * own name, so it never races team-management on a second worker):
 * - TM Alpha: 5 members, captain alpha_1
 * - TM Bravo: 5 members (captain bravo_1) plus stand-in bravo_standin
 * - TM Delta: 5 members, captain delta_1, placement 4 (eliminated)
 *
 * Serial: the repeat takeover replaces the captain the first case brought in.
 */

import type { Locator, Page } from '@playwright/test';
import {
  expect,
  resetTournamentByKey,
  test,
  type TournamentData,
} from '../../fixtures';

const KEY = 'captain_takeover';
const PREFIX = 'tm_fixture_';
const DELTA_CAPTAIN = `${PREFIX}delta_1`;
const BRAVO_CAPTAIN = `${PREFIX}bravo_1`;
const BRAVO_MEMBER = `${PREFIX}bravo_2`;
const ALPHA_MEMBER = `${PREFIX}alpha_2`;
const REPLACE_CAPTAIN_URL = /\/api\/teams\/\d+\/replace-captain\//;

let tournament: TournamentData;

function teamPk(name: string): number {
  const team = tournament.teams.find((t) => t.name === name);
  if (!team) throw new Error(`Team ${name} missing from the ${KEY} reset`);
  return team.pk;
}

async function openManage(page: Page, name: string): Promise<Locator> {
  await page.goto(`/tournament/${tournament.pk}`);
  await page
    .getByTestId('tournamentDetailPage')
    .waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByTestId('teamsTab').click();
  await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });

  const pk = teamPk(name);
  const managed = page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname === `/api/teams/${pk}/`,
  );
  await page
    .getByTestId(`completed-team-card-${pk}`)
    .getByTestId('team-card-name')
    .click();
  const modal = page.getByTestId('team-modal');
  await expect(modal).toBeVisible();
  await managed;
  await modal.getByTestId('team-manage-button').click();
  const dialog = page.getByTestId('team-manage-dialog');
  await expect(dialog).toBeVisible();
  return dialog;
}

function rosterRow(
  dialog: Locator,
  kind: 'member' | 'standin' | 'dropout',
  username: string,
): Locator {
  return dialog
    .locator(`[data-testid^="team-${kind}-row-"]`)
    .filter({ hasText: username });
}

async function expectCaptain(dialog: Locator, username: string): Promise<void> {
  await expect(
    rosterRow(dialog, 'member', username).getByText('Captain', { exact: true }),
  ).toBeVisible();
}

async function openCaptainPicker(page: Page, dialog: Locator): Promise<void> {
  await dialog.getByTestId('team-replace-captain-trigger').click();
  await expect(page.getByTestId('team-captain-search')).toBeVisible();
}

/** Confirms the open Replace captain dialog and waits for its POST. */
async function confirmReplace(page: Page, reason: string): Promise<void> {
  const confirm = page.getByTestId('team-action-dialog');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText('Replace captain?');
  await expect(page.getByTestId('team-action-outgoing-dropout')).toBeChecked();
  await confirm.getByTestId('team-action-reason').fill(reason);
  const posted = page.waitForResponse(
    (r) => r.request().method() === 'POST' && REPLACE_CAPTAIN_URL.test(r.url()),
  );
  await confirm.getByTestId('team-action-confirm').click();
  const response = await posted;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toMatchObject({
    mark_outgoing_dropout: true,
    reason,
  });
  await expect(confirm).toBeHidden();
}

function statusBadge(dialog: Locator): Locator {
  return dialog
    .getByTestId('team-manage-title-row')
    .getByTestId('team-status-badge');
}

test.describe('Captain takeover', () => {
  test.describe.configure({ mode: 'serial', timeout: 60_000 });

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const reset = await resetTournamentByKey(ctx, KEY);
      if (!reset) throw new Error(`Could not reset ${KEY}`);
      tournament = reset;
    } finally {
      await ctx.close();
    }
  });

  test('@cicd eliminated team captain replaces a live captain in one action', async ({
    page,
    loginOrgStaff: login,
  }) => {
    teamPk('TM Delta');
    await login();
    const bravo = await openManage(page, 'TM Bravo');
    await expect(statusBadge(bravo)).toHaveText('In tournament');
    await expect(statusBadge(bravo)).toHaveAttribute('data-status', 'live');

    await openCaptainPicker(page, bravo);
    const freeRow = page
      .locator('[data-testid^="team-captain-free-row-"]')
      .filter({ hasText: DELTA_CAPTAIN });
    await expect(freeRow).toBeVisible();
    await expect(freeRow).toContainText('TM Delta · Eliminated · 4th');
    await expect(freeRow).not.toHaveAttribute('data-disabled', 'true');

    const searched = page.waitForResponse((r) =>
      r.url().includes('/api/users/search/'),
    );
    await page.getByTestId('team-captain-search').fill(ALPHA_MEMBER);
    expect((await searched).status()).toBe(200);
    const alphaRow = page
      .locator('[data-testid^="team-captain-result-"]')
      .filter({ hasText: ALPHA_MEMBER });
    await expect(alphaRow).toBeVisible();
    await expect(alphaRow).toContainText('On TM Alpha');
    await expect(alphaRow).toHaveAttribute('data-disabled', 'true');

    await page.getByTestId('team-captain-search').fill('');
    await freeRow.click();
    await confirmReplace(page, 'Captain left mid-tournament');

    await expectCaptain(bravo, DELTA_CAPTAIN);
    await expect(rosterRow(bravo, 'dropout', BRAVO_CAPTAIN)).toBeVisible();
    await bravo.getByTestId('team-manage-tab-history').click();
    const logged = bravo
      .getByTestId('team-history-row')
      .filter({ hasText: 'Captain left mid-tournament' });
    await expect(logged).toHaveCount(1);
    await expect(logged).toContainText('Replace captain');

    const delta = await openManage(page, 'TM Delta');
    await expect(statusBadge(delta)).toHaveText('Eliminated · 4th');
    await expect(statusBadge(delta)).toHaveAttribute(
      'data-status',
      'eliminated',
    );
    await expectCaptain(delta, DELTA_CAPTAIN);
    await expect(
      delta.locator('[data-testid^="team-member-row-"]'),
    ).toHaveCount(5);
  });

  test('@cicd a brought-in captain is replaced the same way', async ({
    page,
    loginOrgStaff: login,
  }) => {
    await login();
    const bravo = await openManage(page, 'TM Bravo');
    await expectCaptain(bravo, DELTA_CAPTAIN);

    await openCaptainPicker(page, bravo);
    await page.getByTestId('team-captain-search').fill('bravo_2');
    const teamRow = page
      .locator('[data-testid^="team-captain-team-row-"]')
      .filter({ hasText: BRAVO_MEMBER });
    await expect(teamRow).toBeVisible();
    await expect(page.getByText('This team', { exact: true })).toBeVisible();
    await expect(page.getByText('No users found')).toHaveCount(0);
    await teamRow.click();
    await confirmReplace(page, 'Stand-in captain had to leave');

    await expectCaptain(bravo, BRAVO_MEMBER);
    await expect(rosterRow(bravo, 'dropout', DELTA_CAPTAIN)).toBeVisible();
    await expect(rosterRow(bravo, 'dropout', BRAVO_CAPTAIN)).toBeVisible();

    const delta = await openManage(page, 'TM Delta');
    await expectCaptain(delta, DELTA_CAPTAIN);
    await expect(
      delta.locator('[data-testid^="team-member-row-"]'),
    ).toHaveCount(5);
  });
});
