/**
 * Hero draft with the tournament's hero turn timer turned off.
 *
 * The draft snapshots hero_timer_enabled on reset, so the test flips the
 * tournament option, resets the shared two_captain_test draft, and restores
 * both afterwards. Warping far past grace + reserve must not auto-pick.
 */
import { chromium, expect, test, type Page } from '@playwright/test';
import {
  loginAdmin,
  loginAsDiscordId,
  waitForHydration,
} from '../../fixtures/auth';
import { API_URL, BASE_URL } from '../../fixtures/base-url';
import { patchWithCsrf } from '../../fixtures/events';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

test.describe('HeroDraft without a turn timer', () => {
  test('shows no countdowns and never auto-picks', async () => {
    test.setTimeout(180000);

    const browser = await chromium.launch({
      headless: true,
      args: [
        '--disable-web-security',
        '--ignore-certificate-errors',
        '--no-sandbox',
      ],
    });
    const admin = await browser.newContext({ ignoreHTTPSErrors: true });
    const contextA = await browser.newContext({ ignoreHTTPSErrors: true });
    const contextB = await browser.newContext({ ignoreHTTPSErrors: true });
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    const info = await (
      await admin.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
      )
    ).json();
    const draftPk: number = info.pk;
    const tournamentPk: number = info.game.tournament_pk;
    const setHeroTimer = async (enabled: boolean): Promise<void> => {
      const res = await patchWithCsrf(
        admin,
        `${API_URL}/tournaments/${tournamentPk}/`,
        { draft_options: { hero_timer_enabled: enabled } },
      );
      expect(res.ok(), await res.text()).toBe(true);
      await admin.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);
    };
    const currentRound = async (): Promise<number | null> =>
      (
        await (
          await admin.request.get(`${API_URL}/herodraft/${draftPk}/`)
        ).json()
      ).current_round;

    await loginAdmin(admin);
    try {
      await setHeroTimer(false);

      const teams = info.draft_teams;
      await loginAsDiscordId(contextA, teams[0].captain.discordId);
      await loginAsDiscordId(contextB, teams[1].captain.discordId);

      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${info.game.pk}`;
      await Promise.all([pageA.goto(matchUrl), pageB.goto(matchUrl)]);
      await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

      const startBtn = (page: Page) => page.getByTestId('view-draft-btn');
      await Promise.all([startBtn(pageA).click(), startBtn(pageB).click()]);

      const draftA = new HeroDraftPage(pageA);
      const draftB = new HeroDraftPage(pageB);
      await Promise.all([draftA.waitForModal(), draftB.waitForModal()]);
      await Promise.all([
        draftA.waitForConnection(),
        draftB.waitForConnection(),
      ]);

      await draftA.clickReady();
      await draftB.clickReady();
      await Promise.all([
        draftA.waitForPhaseTransition('rolling', 15000),
        draftB.waitForPhaseTransition('rolling', 15000),
      ]);

      await draftA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftA.clickFlipCoin();
      await Promise.all([
        draftA.waitForPhaseTransition('choosing', 15000),
        draftB.waitForPhaseTransition('choosing', 15000),
      ]);

      const aWon = await pageA
        .getByTestId('herodraft-winner-choices')
        .isVisible()
        .catch(() => false);
      const [winner, loser, loserPage] = aWon
        ? [draftA, draftB, pageB]
        : [draftB, draftA, pageA];
      await winner.selectWinnerChoice('first_pick');
      await loserPage
        .getByTestId('herodraft-loser-choices')
        .waitFor({ state: 'visible', timeout: 10000 });
      await loser.selectLoserChoice('radiant');
      await Promise.all([
        draftA.waitForPhaseTransition('drafting', 15000),
        draftB.waitForPhaseTransition('drafting', 15000),
      ]);

      for (const page of [pageA, pageB]) {
        await expect(page.getByTestId('herodraft-no-timer')).toBeVisible();
        await expect(page.getByTestId('herodraft-grace-time')).toHaveCount(0);
      }

      const roundBefore = await currentRound();
      const warp = await admin.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/warp/`,
        { data: { elapsed_ms: 600000, active_reserve_ms: 0 } },
      );
      expect(warp.ok(), await warp.text()).toBe(true);
      // Several 1Hz ticks, each of which would auto-pick with a timer on.
      await pageA.waitForTimeout(4000);
      expect(await currentRound()).toBe(roundBefore);
      await expect(pageA.getByTestId('herodraft-no-timer')).toBeVisible();
    } finally {
      await setHeroTimer(true).catch(() => {});
      await browser.close();
    }
  });
});
