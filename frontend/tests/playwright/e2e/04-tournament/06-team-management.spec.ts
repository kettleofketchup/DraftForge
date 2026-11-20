/**
 * Team management dialog (#546).
 *
 * Uses the dedicated `team_management` tournament (reset once in beforeAll):
 * - TM Alpha: 5 members, captain alpha_1, deputy alpha_2
 * - TM Bravo: 5 members plus stand-in bravo_standin
 * - TM Ghost: 5 members; captain tm_fixture_ghost is on no team
 * - tm_fixture_searchable: a tournament user on no team
 *
 * Serial: each case builds on the previous one's roster changes, and the
 * Reseat case runs last because it clears the ghost captain.
 */

import type { Locator, Page } from '@playwright/test';
import {
  expect,
  loginOrgStaff,
  resetTournamentByKey,
  test,
  type TournamentData,
} from '../../fixtures';

const KEY = 'team_management';
const PREFIX = 'tm_fixture_';
const GHOST = `${PREFIX}ghost`;
const SEARCH_TARGET = `${PREFIX}searchable`;

let tournament: TournamentData;

function teamPk(name: string): number {
  const team = tournament.teams.find((t) => t.name === name);
  if (!team) throw new Error(`Team ${name} missing from the ${KEY} reset`);
  return team.pk;
}

function card(page: Page, name: string): Locator {
  return page.getByTestId(`completed-team-card-${teamPk(name)}`);
}

async function openTeamsTab(page: Page): Promise<void> {
  await page.goto(`/tournament/${tournament.pk}`);
  await page
    .getByTestId('tournamentDetailPage')
    .waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByTestId('teamsTab').click();
  await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
}

/** Opens the team modal from its card and waits for the managed-team GET. */
async function openTeamModal(page: Page, name: string): Promise<Locator> {
  const pk = teamPk(name);
  const managed = page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname === `/api/teams/${pk}/`,
  );
  await card(page, name).getByTestId('team-card-name').click();
  const modal = page.getByTestId('team-modal');
  await expect(modal).toBeVisible();
  await managed;
  return modal;
}

async function openManage(page: Page, name: string): Promise<Locator> {
  const modal = await openTeamModal(page, name);
  await modal.getByTestId('team-manage-button').click();
  const dialog = page.getByTestId('team-manage-dialog');
  await expect(dialog).toBeVisible();
  return dialog;
}

async function confirmAction(page: Page, reason: string): Promise<void> {
  const dialog = page.getByTestId('team-action-dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByTestId('team-action-reason').fill(reason);
  const action = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' && /\/api\/teams\/\d+\//.test(r.url()),
  );
  await dialog.getByTestId('team-action-confirm').click();
  expect((await action).status()).toBe(200);
  await expect(dialog).toBeHidden();
}

/**
 * A card roster row, matched on its avatar: UserStrip truncates names over
 * 20 characters, so the row text can't be matched in full.
 */
function cardRow(
  card: Locator,
  kind: 'member' | 'standin' | 'dropout',
  username: string,
): Locator {
  return card.locator(`[data-testid^="team-card-${kind}-"]`).filter({
    has: card.page().getByRole('img', { name: username, exact: true }),
  });
}

function memberRow(dialog: Locator, username: string): Locator {
  return dialog
    .locator('[data-testid^="team-member-row-"]')
    .filter({ hasText: username });
}

test.describe('Team management dialog', () => {
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

  test('@cicd non-staff sees no manage button or leadership flags', async ({
    browser,
    page,
    loginUser,
  }) => {
    const staffCtx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginOrgStaff(staffCtx);
      const staff = await staffCtx.newPage();
      await openTeamsTab(staff);
      await expect(
        card(staff, 'TM Ghost').getByTestId('team-leadership-problem'),
      ).toBeVisible();
      const staffModal = await openTeamModal(staff, 'TM Ghost');
      await expect(staffModal.getByTestId('team-manage-button')).toBeVisible();
    } finally {
      await staffCtx.close();
    }

    await loginUser();
    await openTeamsTab(page);
    await expect(card(page, 'TM Ghost')).toBeVisible();
    const modal = await openTeamModal(page, 'TM Ghost');
    await expect(modal.getByTestId('team-modal-captain')).toContainText(GHOST);
    await expect(modal.getByTestId('team-manage-button')).toHaveCount(0);
    await expect(page.getByTestId('team-leadership-problem')).toHaveCount(0);
    await expect(page.getByTestId('team-leadership-alert')).toHaveCount(0);
  });

  test('@cicd league staff see leadership flags and can search stand-ins', async ({
    page,
    loginLeagueStaff,
  }) => {
    await loginLeagueStaff();
    await openTeamsTab(page);
    const alert = page.getByTestId('team-leadership-alert');
    await expect(alert).toBeVisible();
    await expect(
      alert.getByTestId(`team-leadership-alert-row-${teamPk('TM Ghost')}`),
    ).toBeVisible();
    await expect(
      card(page, 'TM Ghost').getByTestId('team-leadership-problem'),
    ).toBeVisible();

    const dialog = await openManage(page, 'TM Alpha');
    await dialog.getByRole('button', { name: 'Add stand-in' }).click();
    const search = page.getByTestId('team-standin-search');
    const searched = page.waitForResponse((r) =>
      r.url().includes('/api/users/search/'),
    );
    await search.fill(SEARCH_TARGET);
    expect((await searched).status()).toBe(200);
    await expect(
      page
        .locator('[data-testid^="team-standin-result-"]')
        .filter({ hasText: SEARCH_TARGET }),
    ).toBeVisible();
  });

  test('@cicd org staff change captain with a reason', async ({
    page,
    loginOrgStaff: login,
  }) => {
    await login();
    await openTeamsTab(page);
    const alpha = card(page, 'TM Alpha');
    await expect(alpha).toContainText(`Captain: ${PREFIX}alpha_1`);

    const dialog = await openManage(page, 'TM Alpha');
    await memberRow(dialog, `${PREFIX}alpha_3`)
      .getByRole('button', { name: 'Make captain' })
      .click();
    await confirmAction(page, 'Captain asked to step down');

    await expect(
      memberRow(dialog, `${PREFIX}alpha_3`).getByText('Captain', {
        exact: true,
      }),
    ).toBeVisible();
    await expect(alpha).toContainText(`Captain: ${PREFIX}alpha_3`);
  });

  test('@cicd mark dropout then sub in a stand-in', async ({
    page,
    loginOrgStaff: login,
  }) => {
    await login();
    await openTeamsTab(page);
    const bravo = card(page, 'TM Bravo');
    const standin = `${PREFIX}bravo_standin`;
    const dropout = `${PREFIX}bravo_5`;
    await expect(cardRow(bravo, 'standin', standin)).toBeVisible();

    const dialog = await openManage(page, 'TM Bravo');
    await memberRow(dialog, dropout)
      .getByRole('button', { name: 'Mark dropout' })
      .click();
    await confirmAction(page, 'Left for the evening');
    await expect(
      dialog
        .locator('[data-testid^="team-dropout-row-"]')
        .filter({ hasText: dropout }),
    ).toBeVisible();
    await expect(cardRow(bravo, 'dropout', dropout)).toBeVisible();

    await dialog
      .locator('[data-testid^="team-standin-row-"]')
      .filter({ hasText: standin })
      .getByRole('button', { name: 'Sub in' })
      .click();
    await expect(page.getByTestId('team-action-replacing')).toContainText(
      'No one',
    );
    await confirmAction(page, 'Covering the open slot');
    await expect(memberRow(dialog, standin)).toBeVisible();
    await expect(
      dialog.locator('[data-testid^="team-standin-row-"]'),
    ).toHaveCount(0);
    await expect(cardRow(bravo, 'member', standin)).toBeVisible();
    await expect(
      bravo.locator('[data-testid^="team-card-standin-"]'),
    ).toHaveCount(0);
  });

  test('@cicd history tab shows actor, action and reason', async ({
    page,
    loginOrgStaff: login,
  }) => {
    await login();
    await openTeamsTab(page);
    const dialog = await openManage(page, 'TM Alpha');
    await dialog.getByTestId('team-manage-tab-history').click();
    const row = dialog
      .getByTestId('team-history-row')
      .filter({ hasText: 'Captain asked to step down' });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('Set captain');
    await expect(row).toContainText(/Org Staff Tester|org_staff_tester/);
    await expect(row).toContainText(`${PREFIX}alpha_3`);
  });

  test('@cicd ghost captain is fixed from the Teams-tab alert', async ({
    page,
    loginOrgStaff: login,
  }) => {
    await login();
    await openTeamsTab(page);
    const ghostPk = teamPk('TM Ghost');
    const ghost = card(page, 'TM Ghost');
    await expect(ghost.getByTestId('team-leadership-problem')).toBeVisible();

    const managed = page.waitForResponse(
      (r) =>
        r.request().method() === 'GET' &&
        new URL(r.url()).pathname === `/api/teams/${ghostPk}/`,
    );
    await page
      .getByTestId(`team-leadership-alert-row-${ghostPk}`)
      .getByRole('button', { name: 'Review TM Ghost' })
      .click();
    const modal = page.getByTestId('team-modal');
    await expect(modal).toBeVisible();
    await managed;
    await modal.getByTestId('team-manage-button').click();
    const dialog = page.getByTestId('team-manage-dialog');
    await expect(dialog.getByTestId('team-leadership-banner')).toBeVisible();

    await dialog
      .getByRole('button', { name: `Reseat ${GHOST} as member` })
      .click();
    await confirmAction(page, 'Captain was never added to the roster');

    await expect(dialog.getByTestId('team-leadership-banner')).toHaveCount(0);
    await expect(memberRow(dialog, GHOST)).toBeVisible();
    await expect(ghost.getByTestId('team-leadership-problem')).toHaveCount(0);
    await expect(
      page.getByTestId(`team-leadership-alert-row-${ghostPk}`),
    ).toHaveCount(0);
  });
});
