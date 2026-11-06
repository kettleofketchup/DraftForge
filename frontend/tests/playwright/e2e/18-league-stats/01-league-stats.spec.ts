import type { BrowserContext, Locator, Page } from '@playwright/test';
import { test, expect, getTournamentByKey } from '../../fixtures';
import { TournamentPage } from '../../helpers/tournament';

const NAMES = {
  ace: 'Strip Ace',
  hot: 'Strip Hot',
  tieA: 'Strip Tie A',
  tieB: 'Strip Tie B',
  cold: 'Strip Cold',
  mid: 'Strip Mid',
  rookie: 'Strip Rookie',
  zero: 'Strip Zero',
  captA: 'Strip Capt A',
  captB: 'Strip Capt B',
} as const;

const L_BADGE_NAMES = [NAMES.ace, NAMES.hot, NAMES.tieA, NAMES.tieB];
const NO_L_BADGE_NAMES = [NAMES.cold, NAMES.mid, NAMES.rookie, NAMES.zero];

interface StripStatsTournament {
  pk: number;
  leaguePk: number;
}

async function resolveTournament(context: BrowserContext): Promise<StripStatsTournament> {
  const tournament = await getTournamentByKey(context, 'strip_stats');
  if (!tournament) {
    throw new Error('strip_stats tournament missing. Run: just db::populate::fresh');
  }
  if (tournament.league_pk == null) {
    throw new Error('strip_stats tournament has no league_pk');
  }
  return { pk: tournament.pk, leaguePk: tournament.league_pk };
}

function summariesResponse(page: Page, leaguePk: number) {
  return page.waitForResponse(
    (r) => r.url().includes(`/api/steam/leagues/${leaguePk}/player-summaries/`) && r.ok(),
  );
}

async function openTeamsTab(page: Page, t: StripStatsTournament): Promise<TournamentPage> {
  const summaries = summariesResponse(page, t.leaguePk);
  const tournamentPage = new TournamentPage(page);
  await tournamentPage.goto(t.pk, 'teams');
  await tournamentPage.teamsTabContent.waitFor({ state: 'visible' });
  await summaries;
  return tournamentPage;
}

async function openDraftModal(page: Page, t: StripStatsTournament): Promise<Locator> {
  const tournamentPage = await openTeamsTab(page, t);
  await tournamentPage.clickStartDraft();
  await tournamentPage.waitForDraftModal();
  const dialog = page
    .getByRole('dialog')
    .filter({ has: page.getByTestId('available-player') });
  await expect(dialog).toBeVisible();
  return dialog;
}

function availableStrip(dialog: Locator, name: string): Locator {
  return dialog
    .getByTestId('available-player')
    .filter({ visible: true })
    .filter({ has: dialog.page().getByText(name, { exact: true }) });
}

function teamCard(page: Page, name: string): Locator {
  return page
    .locator('[data-testid^="completed-team-card-"]')
    .filter({ visible: true })
    .filter({ has: page.getByText(name, { exact: true }) });
}

function nameTrigger(strip: Locator, name: string): Locator {
  return strip.getByRole('button', { name: `View profile for ${name}` }).last();
}

function avatarTrigger(strip: Locator, name: string): Locator {
  return strip.getByRole('button', { name: `View profile for ${name}` }).first();
}

async function expectAceVisible(dialog: Locator): Promise<void> {
  const ace = availableStrip(dialog, NAMES.ace);
  await expect(ace).toHaveCount(1);
  await expect(ace.getByTestId('strip-league-stats')).toBeVisible();
}

async function expectHiddenByDesign(dialog: Locator): Promise<void> {
  const ace = availableStrip(dialog, NAMES.ace);
  await expect(ace).toHaveCount(1);
  await expect(ace).toBeVisible();
  await expect(ace.getByTestId('strip-league-stats')).toBeAttached();
  await expect(dialog.getByTestId('strip-league-stats').filter({ visible: true })).toHaveCount(0);
}

interface Box {
  label: string;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

interface Fit {
  label: string;
  scrollWidth: number;
  clientWidth: number;
}

interface StripLayout {
  width: number;
  fits: Fit[];
  outer: Box;
  parts: Box[];
}

const STATS_ONLY_AT_1920 =
  'strip-league-stats is container-hidden at 1024 and 1280 in the draft modal; only 1920 measures stats against name/MMR/action';

function draftStrips(dialog: Locator): Locator {
  return dialog
    .locator('[data-testid="available-player"]:has([aria-label^="View profile for"])')
    .filter({ visible: true });
}

function teamCardStrips(card: Locator): Locator {
  return card
    .locator('[class~="@container"]:has([aria-label^="View profile for"])')
    .filter({ visible: true });
}

async function measureStrips(strips: Locator): Promise<StripLayout[]> {
  return strips.evaluateAll((strips) =>
      strips.map((strip) => {
        const box = (label: string, el: Element): Box => {
          const r = el.getBoundingClientRect();
          return { label, left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        };
        const parts: Box[] = [];
        const triggers = strip.querySelectorAll('[aria-label^="View profile for"]');
        const nameSpan = triggers[triggers.length - 1]?.firstElementChild;
        if (nameSpan) parts.push(box('name', nameSpan));
        const children = Array.from(strip.children);
        const mmr = children.find((c) => c.textContent?.includes('B:'));
        if (mmr) parts.push(box('mmr', mmr));
        const fit = (label: string, el: Element): Fit => ({
          label,
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        });
        const fits: Fit[] = [fit('strip', strip)];
        const stats = strip.querySelector('[data-testid="strip-league-stats"]');
        if (stats && stats.getBoundingClientRect().width > 0) {
          parts.push(box('stats', stats));
          fits.push(fit('stats', stats));
          const badge = stats.querySelector('[data-testid="strip-league-stats-rank"]')?.parentElement;
          if (badge) fits.push(fit('stats badge', badge));
        }
        const last = children[children.length - 1];
        if (last && last.classList.contains('flex-1')) {
          const context = last.firstElementChild;
          if (context && context.getBoundingClientRect().width > 0) parts.push(box('context', context));
        } else if (last && last.getBoundingClientRect().width > 0) {
          parts.push(box('action', last));
        }
        return {
          width: strip.getBoundingClientRect().width,
          fits,
          outer: box('strip', strip),
          parts,
        };
      }),
    );
}

function overlaps(a: Box, b: Box): boolean {
  return a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
}

function inside(inner: Box, outer: Box): boolean {
  return (
    inner.left >= outer.left - 0.5 &&
    inner.right <= outer.right + 0.5 &&
    inner.top >= outer.top - 0.5 &&
    inner.bottom <= outer.bottom + 0.5
  );
}

function expectCleanLayout(layouts: StripLayout[], where: string): void {
  expect(layouts.length, `strips at ${where}`).toBeGreaterThan(0);
  for (const layout of layouts) {
    for (const f of layout.fits) {
      expect(f.scrollWidth, `${f.label} scrollWidth at ${where}`).toBeLessThanOrEqual(f.clientWidth);
    }
    for (const part of layout.parts) {
      expect(inside(part, layout.outer), `${part.label} inside strip at ${where}`).toBe(true);
    }
    for (let i = 0; i < layout.parts.length; i++) {
      for (let j = i + 1; j < layout.parts.length; j++) {
        const a = layout.parts[i];
        const b = layout.parts[j];
        expect(overlaps(a, b), `${a.label}/${b.label} overlap at ${where}`).toBe(false);
      }
    }
  }
}

function statsBadge(stats: Locator): Locator {
  return stats.getByTestId('strip-league-stats-rank').locator('xpath=..');
}

function winRateChip(stats: Locator): Locator {
  return statsBadge(stats).locator('span').filter({ hasText: /^\d+%$/ });
}

test.describe('Strip league stats (@cicd)', () => {
  let tournament: StripStatsTournament;

  test.beforeEach(async ({ context, loginAdmin }) => {
    await loginAdmin();
    tournament = await resolveTournament(context);
  });

  test.describe('1920 wide', () => {
    test.use({ viewport: { width: 1920, height: 1000 } });

    test('@1920 draft modal shows stats', async ({ page }) => {
      const dialog = await openDraftModal(page, tournament);
      await expectAceVisible(dialog);

      const ace = availableStrip(dialog, NAMES.ace);
      const aceStats = ace.getByTestId('strip-league-stats');
      await expect(statsBadge(aceStats)).toHaveText('#1 · 8g · 88%');
      await expect(winRateChip(aceStats)).toHaveClass(/\btext-success\b/);
      await expect(winRateChip(aceStats)).not.toHaveClass(/destructive/);

      const midStats = availableStrip(dialog, NAMES.mid).getByTestId('strip-league-stats');
      await expect(statsBadge(midStats)).toHaveText('#6 · 7g · 29%');
      await expect(winRateChip(midStats)).toHaveClass(/\bbg-destructive\//);
      await expect(winRateChip(midStats)).not.toHaveClass(/text-success/);
      await expect(ace.getByTestId('streak-badge')).toHaveCount(0);
      const form = await ace
        .getByTestId('recent-form')
        .locator('[data-result]')
        .evaluateAll((els) => els.map((el) => el.getAttribute('data-result')));
      expect(form).toEqual(['W', 'W', 'W', 'L', 'W']);

      await expect(availableStrip(dialog, NAMES.hot).getByTestId('streak-badge')).toHaveText('W4');
      await expect(availableStrip(dialog, NAMES.cold).getByTestId('streak-badge')).toHaveText('L3');

      const rookieStats = availableStrip(dialog, NAMES.rookie).getByTestId('strip-league-stats');
      await expect(rookieStats).toBeVisible();
      await expect(rookieStats).toContainText('3g ·');
      await expect(rookieStats).not.toContainText('#');

      const zero = availableStrip(dialog, NAMES.zero);
      await expect(zero).toBeVisible();
      await expect(zero.getByTestId('strip-league-stats')).toHaveCount(0);
    });

    test('modal from click', async ({ page }) => {
      const dialog = await openDraftModal(page, tournament);
      await expectAceVisible(dialog);

      await nameTrigger(availableStrip(dialog, NAMES.ace), NAMES.ace).click();
      const summary = page.getByTestId('player-league-summary');
      await expect(summary).toBeVisible();
      await expect(summary).toContainText('#1 / 7');
      await expect(summary).toContainText('top 15%');
      await expect(
        summary.getByTestId('win-rate-histogram').locator('[data-highlighted="true"]'),
      ).toHaveCount(1);
      await expect(summary).toContainText(/KDA .* · GPM \d+ · XPM \d+/);

      await page.keyboard.press('Escape');
      await expect(summary).toBeHidden();

      await nameTrigger(availableStrip(dialog, NAMES.rookie), NAMES.rookie).click();
      await expect(page.getByTestId('player-league-summary')).toContainText('— / 7');
    });

    test('modal from hover card', async ({ page }) => {
      await openTeamsTab(page, tournament);
      const card = teamCard(page, NAMES.captA);
      await expect(card.getByTestId('strip-league-stats')).toBeVisible();

      await avatarTrigger(card, NAMES.captA).hover();
      const hoverCard = page.getByRole('tooltip').filter({ hasText: NAMES.captA });
      await expect(hoverCard).toBeVisible();
      await hoverCard.click();
      const summary = page.getByTestId('player-league-summary');
      await expect(summary).toBeVisible();
      await expect(summary).toContainText('#7 / 7');
    });

    test('L: badge regression', async ({ page }) => {
      const dialog = await openDraftModal(page, tournament);
      await expectAceVisible(dialog);

      for (const name of L_BADGE_NAMES) {
        const strip = availableStrip(dialog, name);
        await expect(strip, name).toContainText('L:');
        await expect(strip, name).toContainText('B:');
      }
      for (const name of NO_L_BADGE_NAMES) {
        const strip = availableStrip(dialog, name);
        await expect(strip, name).toHaveCount(1);
        await expect(strip, name).not.toContainText('L:');
        await expect(strip, name).toContainText('B:');
      }

      await openTeamsTab(page, tournament);
      for (const name of [NAMES.captA, NAMES.captB]) {
        const strip = teamCard(page, name);
        await expect(strip, name).toHaveCount(1);
        await expect(strip, name).not.toContainText('L:');
        await expect(strip, name).toContainText('B:');
      }
    });
  });

  test.describe('1280 wide', () => {
    test.use({ viewport: { width: 1280, height: 1000 } });

    test('@1280 draft modal hides by design', async ({ page }) => {
      const dialog = await openDraftModal(page, tournament);
      await expectHiddenByDesign(dialog);
    });

    test('@1280 TeamsTab shows strip_capt_a stats', async ({ page }) => {
      await openTeamsTab(page, tournament);
      const capt = teamCard(page, NAMES.captA);
      await expect(capt).toHaveCount(1);
      const stats = capt.getByTestId('strip-league-stats');
      await expect(stats).toBeVisible();
      await expect(statsBadge(stats)).toHaveText('#7 · 5g · 20%');

      const cards = page.locator('[data-testid^="completed-team-card-"]').filter({ visible: true });
      const layouts = await measureStrips(teamCardStrips(cards));
      expectCleanLayout(layouts, 'TeamsTab 1280');
      expect(layouts.some((l) => l.parts.some((p) => p.label === 'stats'))).toBe(true);
      expect(layouts.some((l) => l.parts.some((p) => p.label === 'context'))).toBe(true);

      const captB = teamCard(page, NAMES.captB);
      await expect(captB).toBeVisible();
      await expect(captB.getByTestId('strip-league-stats')).toHaveCount(0);
    });
  });

  test('no overflow/overlap at 1024, 1280, 1920', async ({ page }) => {
    const measured: Record<number, number[]> = {};
    for (const width of [1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      const dialog = await openDraftModal(page, tournament);
      if (width === 1920) {
        await expectAceVisible(dialog);
      } else {
        await expect(availableStrip(dialog, NAMES.ace)).toBeVisible();
      }

      const layouts = await measureStrips(draftStrips(dialog));
      measured[width] = [...new Set(layouts.map((l) => Math.round(l.width)))];
      expectCleanLayout(layouts, String(width));
      if (width === 1920) {
        expect(layouts.some((l) => l.parts.some((p) => p.label === 'stats'))).toBe(true);
        expect(layouts.some((l) => l.fits.some((f) => f.label === 'stats badge'))).toBe(true);
      }
    }
    test.info().annotations.push({ type: 'strip-widths', description: JSON.stringify(measured) });
    test.info().annotations.push({ type: 'stats-geometry', description: STATS_ONLY_AT_1920 });
  });

  test.describe('375 wide', () => {
    test.use({ viewport: { width: 375, height: 1000 } });

    test('@375 hidden', async ({ page }) => {
      const dialog = await openDraftModal(page, tournament);
      await expectHiddenByDesign(dialog);
    });
  });
});
