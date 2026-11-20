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
 * A card roster row, matched on its avatar's alt text: UserStrip truncates
 * names over 20 characters, and the open manage dialog aria-hides the card,
 * so neither row text nor role queries can find it.
 */
function cardRow(
  card: Locator,
  kind: 'member' | 'standin' | 'dropout',
  username: string,
): Locator {
  return card.locator(`[data-testid^="team-card-${kind}-"]`).filter({
    has: card.page().locator(`img[alt="${username}"]`),
  });
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

function memberRow(dialog: Locator, username: string): Locator {
  return rosterRow(dialog, 'member', username);
}

/** Matches DataTableRowActions `inlineFrom="md"`: inline buttons from 768 px, the menu below. */
const INLINE_ACTIONS_MIN_WIDTH = 768;

function actionsInline(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) >= INLINE_ACTIONS_MIN_WIDTH;
}

/** Runs a roster row action: its inline button, or the menu item on phones. */
async function rowAction(row: Locator, label: string): Promise<void> {
  if (actionsInline(row.page())) {
    await row
      .getByRole('group', { name: /^Actions for / })
      .getByRole('button', { name: label, exact: true })
      .click();
    return;
  }
  await row.getByRole('button', { name: /^Actions for / }).click();
  await row.page().getByRole('menuitem', { name: label, exact: true }).click();
}

/** The warning icon, avatar and name share one line inside `container`, in that order. */
async function expectIconInline(container: Locator): Promise<void> {
  const icon = await container.locator('svg').first().boundingBox();
  const avatar = await container
    .getByTestId('leader-option-avatar')
    .boundingBox();
  const label = await container.getByTestId('leader-option-name').boundingBox();
  if (!icon || !avatar || !label) {
    throw new Error('icon, avatar or label is not rendered');
  }
  for (const box of [icon, avatar]) {
    const mid = box.y + box.height / 2;
    expect(mid).toBeGreaterThan(label.y);
    expect(mid).toBeLessThan(label.y + label.height);
  }
  expect(icon.x + icon.width).toBeLessThanOrEqual(avatar.x);
  expect(avatar.x + avatar.width).toBeLessThanOrEqual(label.x);
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
    await rowAction(memberRow(dialog, `${PREFIX}alpha_3`), 'Make captain');
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
    await rowAction(memberRow(dialog, dropout), 'Mark dropout');
    await confirmAction(page, 'Left for the evening');
    await expect(rosterRow(dialog, 'dropout', dropout)).toBeVisible();
    await expect(cardRow(bravo, 'dropout', dropout)).toBeVisible();

    await rowAction(rosterRow(dialog, 'standin', standin), 'Sub in');
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

  for (const width of [390, 1440]) {
    test(`@cicd ghost captain icon sits inline at ${width} px`, async ({
      page,
      loginOrgStaff: login,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await login();
      await page.goto(`/tournament/${tournament.pk}/teams`);
      await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
      const dialog = await openManage(page, 'TM Ghost');
      const trigger = dialog.getByTestId('team-manage-captain-select');
      await expect(trigger).toContainText(`${GHOST} (not a member)`);
      await expectIconInline(trigger.locator('[data-slot="select-value"]'));
      await testInfo.attach(`captain-trigger-${width}`, {
        body: await trigger.screenshot(),
        contentType: 'image/png',
      });

      const row = memberRow(dialog, `${PREFIX}charlie_1`);
      const menu = row.getByRole('button', { name: /^Actions for / });
      const inline = row.getByRole('button', { name: 'Make captain' });
      if (width >= INLINE_ACTIONS_MIN_WIDTH) {
        await expect(inline).toBeVisible();
        await expect(menu).toHaveCount(0);
      } else {
        await expect(menu).toBeVisible();
        await expect(inline).toHaveCount(0);
      }

      await trigger.click();
      const item = page
        .getByRole('option')
        .filter({ hasText: `${GHOST} (not a member)` });
      await expect(item).toBeVisible();
      await expectIconInline(item.locator(':scope > span').last());
      await testInfo.attach(`captain-list-${width}`, {
        body: await page.locator('[data-slot="select-content"]').screenshot(),
        contentType: 'image/png',
      });
    });
  }

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
