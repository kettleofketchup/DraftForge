/**
 * Grace + reserve urgency animation classes.
 *
 * Two thresholds drive distinct CSS animations in DraftTopBar:
 *   - graceRemaining < 10s            → .animate-grace-urgent  (red ↔ yellow)
 *   - graceRemaining === 0 AND
 *     active team's reserve < 30s    → .animate-reserve-critical (red ↔ white)
 *
 * Driven by /api/tests/herodraft/<pk>/warp/ to skip the 25-90s of real-time
 * waiting needed to reach each threshold organically.
 */
import { test, expect, chromium, type Page } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

test.describe('HeroDraft Timer Urgency Animations', () => {
  test('grace<10s pulses grace-urgent; grace=0 + reserve<30s pulses reserve-critical', async () => {
    test.setTimeout(180000);

    const browser = await chromium.launch({
      headless: true,
      args: [
        '--disable-web-security',
        '--ignore-certificate-errors',
        '--no-sandbox',
      ],
    });

    const contextA = await browser.newContext({ ignoreHTTPSErrors: true });
    const contextB = await browser.newContext({ ignoreHTTPSErrors: true });
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    try {
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 },
      );
      if (!response.ok()) {
        throw new Error(`Failed to get test data: ${response.status()}`);
      }
      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;

      await contextA.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/reset/`,
        { failOnStatusCode: false },
      );

      await loginAsDiscordId(contextA, teams[0].captain.discordId);
      await loginAsDiscordId(contextB, teams[1].captain.discordId);

      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      await Promise.all([pageA.goto(matchUrl), pageB.goto(matchUrl)]);
      await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

      const startBtn = (page: Page) => page.getByTestId('view-draft-btn');
      await Promise.all([startBtn(pageA).click(), startBtn(pageB).click()]);

      const draftPageA = new HeroDraftPage(pageA);
      const draftPageB = new HeroDraftPage(pageB);

      await Promise.all([draftPageA.waitForModal(), draftPageB.waitForModal()]);
      await Promise.all([
        draftPageA.waitForConnection(),
        draftPageB.waitForConnection(),
      ]);

      await draftPageA.clickReady();
      await draftPageB.clickReady();

      await Promise.all([
        draftPageA.waitForPhaseTransition('rolling', 15000),
        draftPageB.waitForPhaseTransition('rolling', 15000),
      ]);

      await draftPageA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftPageA.clickFlipCoin();

      await Promise.all([
        draftPageA.waitForPhaseTransition('choosing', 15000),
        draftPageB.waitForPhaseTransition('choosing', 15000),
      ]);

      const winnerChoices = pageA.locator('[data-testid="herodraft-winner-choices"]');
      const isAWinner = await winnerChoices.isVisible().catch(() => false);
      if (isAWinner) {
        await draftPageA.selectWinnerChoice('first_pick');
        const loserChoices = pageB.locator('[data-testid="herodraft-loser-choices"]');
        await loserChoices.waitFor({ state: 'visible', timeout: 10000 });
        await draftPageB.selectLoserChoice('radiant');
      } else {
        await draftPageB.selectWinnerChoice('first_pick');
        const loserChoices = pageA.locator('[data-testid="herodraft-loser-choices"]');
        await loserChoices.waitFor({ state: 'visible', timeout: 10000 });
        await draftPageA.selectLoserChoice('radiant');
      }

      await Promise.all([
        draftPageA.waitForPhaseTransition('drafting', 15000),
        draftPageB.waitForPhaseTransition('drafting', 15000),
      ]);

      // ── Scenario 1: grace-urgent (under 10s remaining, reserve untouched) ──
      // Default grace = 30s. Warp elapsed to 22s → graceRemaining = 8s.
      await contextA.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/warp/`,
        { data: { elapsed_ms: 22000 }, failOnStatusCode: false },
      );

      const graceTimeA = pageA.locator('[data-testid="herodraft-grace-time"]');
      const graceTimeB = pageB.locator('[data-testid="herodraft-grace-time"]');

      // Wait for the next 1Hz tick to land + rAF to repaint.
      await expect
        .poll(
          async () => {
            const cls = await graceTimeA.getAttribute('class');
            return cls?.includes('animate-grace-urgent') ?? false;
          },
          {
            timeout: 5000,
            message: 'grace-urgent class did not appear after warp to <10s',
          },
        )
        .toBe(true);

      const graceTextA = (await graceTimeA.textContent()) ?? '';
      const [m, s] = graceTextA.split(':').map(Number);
      expect(m * 60 + s).toBeLessThan(10);

      // Captain B sees it too — class applied client-side from the same anchors.
      await expect(graceTimeB).toHaveClass(/animate-grace-urgent/);

      // ── Scenario 2: reserve-critical (grace=0, active team's reserve <30s) ──
      // elapsed=32000 → grace exhausted by 2s. active_reserve_ms=25000 →
      // displayed reserve = 25000 - 2000 = 23000 (<30s). Safe from auto-pick
      // (total = grace 30 + reserve 25 = 55s; we're at 32s).
      await contextA.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/warp/`,
        {
          data: { elapsed_ms: 32000, active_reserve_ms: 25000 },
          failOnStatusCode: false,
        },
      );

      // The active team's reserve span carries the critical class. Find
      // whichever side (A or B) is the active picker — the topbar
      // applies the class only there.
      const reserveASpan = pageA.locator('[data-testid="herodraft-team-a-reserve-time"]');
      const reserveBSpan = pageA.locator('[data-testid="herodraft-team-b-reserve-time"]');

      await expect
        .poll(
          async () => {
            const aCls = (await reserveASpan.getAttribute('class')) ?? '';
            const bCls = (await reserveBSpan.getAttribute('class')) ?? '';
            return (
              aCls.includes('animate-reserve-critical') ||
              bCls.includes('animate-reserve-critical')
            );
          },
          {
            timeout: 5000,
            message:
              'reserve-critical class did not appear on either team reserve after warp',
          },
        )
        .toBe(true);

      // Grace must read 0:00 in this state.
      await expect(graceTimeA).toHaveText('0:00');

      // Sanity: only the ACTIVE team's reserve carries the class.
      const aHas = ((await reserveASpan.getAttribute('class')) ?? '').includes(
        'animate-reserve-critical',
      );
      const bHas = ((await reserveBSpan.getAttribute('class')) ?? '').includes(
        'animate-reserve-critical',
      );
      expect(aHas === bHas).toBe(false);
    } finally {
      await browser.close();
    }
  });
});
