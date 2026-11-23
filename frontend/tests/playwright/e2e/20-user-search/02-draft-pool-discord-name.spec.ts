/**
 * The draft's available-players search matches a player's Discord global name,
 * not only username and site nickname. No populated draft-pool user has a
 * Discord name, so the tournament response and the draft and tournament
 * websocket frames give one available player a name found nowhere in their
 * username or nickname.
 */

import type { Locator } from '@playwright/test';

import { expect, getTournamentByKey, test } from '../../fixtures';
import { TournamentPage } from '../../helpers/tournament';

const DISCORD_NAME = 'Zephyr Moonwhisper';

let tournamentPk: number;
let targetPk: number;

function memberPks(members: unknown[] | undefined): number[] {
  return (members ?? []).map((m) =>
    typeof m === 'number' ? m : (m as { pk: number }).pk,
  );
}

// Sets the Discord name on every user object for targetPk in a payload.
function withDiscordName(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withDiscordName);
  if (value === null || typeof value !== 'object') return value;
  const obj = value as Record<string, unknown>;
  for (const key of Object.keys(obj)) obj[key] = withDiscordName(obj[key]);
  if (obj.pk === targetPk && 'username' in obj) {
    obj.discordNickname = DISCORD_NAME;
  }
  return obj;
}

function searchBox(dialog: Locator): Locator {
  return dialog.getByPlaceholder('Search players...').filter({ visible: true });
}

function visibleStrips(dialog: Locator): Locator {
  return dialog.getByTestId('available-player').filter({ visible: true });
}

test.describe('Draft pool search by Discord name (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'draft_captain_turn');
    await context.close();
    if (!tournament) {
      throw new Error(
        'draft_captain_turn missing. Run: just db::populate::all',
      );
    }
    tournamentPk = tournament.pk;
    const drafted = new Set(
      (tournament.teams ?? []).flatMap((t) => memberPks(t.members)),
    );
    const available = memberPks(tournament.users).filter(
      (pk) => !drafted.has(pk),
    );
    if (available.length < 2) {
      throw new Error('draft_captain_turn needs 2+ available players');
    }
    targetPk = available[available.length - 1];
  });

  test.beforeEach(async ({ page, loginAdmin }) => {
    await loginAdmin();
    await page.route(`**/api/tournaments/${tournamentPk}/`, async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        json: withDiscordName(await response.json()),
      });
    });
    for (const url of [
      '**/api/draft/**',
      `**/api/tournament/${tournamentPk}/`,
    ]) {
      await page.routeWebSocket(url, (ws) => {
        const server = ws.connectToServer();
        ws.onMessage((message) => server.send(message));
        server.onMessage((message) => {
          try {
            ws.send(
              JSON.stringify(withDiscordName(JSON.parse(String(message)))),
            );
          } catch {
            ws.send(message);
          }
        });
      });
    }
  });

  test('finds a player by a Discord name absent from username and nickname', async ({
    page,
  }) => {
    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournamentPk, 'teams');
    await tournamentPage.teamsTabContent.waitFor({ state: 'visible' });
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    const dialog = page
      .getByRole('dialog')
      .filter({ has: page.getByPlaceholder('Search players...') });
    await expect(dialog).toBeVisible();

    const count = dialog
      .getByTestId('available-players-count')
      .filter({ visible: true });
    await expect(
      visibleStrips(dialog).filter({ hasText: DISCORD_NAME }).first(),
    ).toBeVisible();
    await expect(count).not.toContainText(/^1\//);

    await searchBox(dialog).fill('moonwhisp');
    await expect(count).toContainText(/^1\//);
    await expect(visibleStrips(dialog).first()).toContainText(DISCORD_NAME);

    await searchBox(dialog).fill('zzz-no-such-player');
    await expect(count).toContainText(/^0\//);
  });
});
