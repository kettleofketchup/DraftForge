/**
 * Desktop/tablet navbar width sweep (#252): no navbar item may overlap
 * another, truncate its label or spill out of the bar, at any width from md
 * up to 2560px, logged in or out, with or without the preview login buttons,
 * once the GitHub star badge has loaded.
 */
import fs from 'node:fs';
import path from 'node:path';
import type { Browser, BrowserContext, Page } from '@playwright/test';
import { test, expect, loginAdmin } from '../fixtures';

// Screenshotted widths; the sweep also walks every 16px between them so a
// breakpoint can't hide a collision between two sampled widths.
const WIDTHS = [768, 900, 1024, 1100, 1180, 1280, 1366, 1440, 1536, 1680, 1920, 2560];
const SWEEP = [...new Set([...WIDTHS, ...Array.from({ length: 113 }, (_, i) => 768 + i * 16)])].sort(
  (a, b) => a - b,
);
const STAR_COUNT = 1234;
const SHOT_DIR = process.env.NAVBAR_SHOT_DIR;

type Box = { label: string; x: number; y: number; w: number; h: number };
type Measurement = {
  boxes: Box[];
  navLeft: number;
  navRight: number;
  truncated: string[];
  overflowingGroups: number;
  pageOverflow: boolean;
};

async function openNavbar(
  browser: Browser,
  opts: { loggedIn: boolean; preview: boolean; locale: 'en' | 'es' },
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    viewport: { width: WIDTHS[0], height: 800 },
    locale: opts.locale === 'es' ? 'es-ES' : 'en-US',
  });
  // The preview login buttons hide themselves when window.playwright is set.
  if (!opts.preview) {
    await context.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
  }
  await context.route('https://api.github.com/repos/**', (route) =>
    route.fulfill({ json: { stargazers_count: STAR_COUNT } }),
  );
  if (opts.loggedIn) await loginAdmin(context);

  const page = await context.newPage();
  await page.goto('/tournaments');
  const account = opts.loggedIn
    ? page.locator('header [data-testid="user-avatar"]')
    : page.locator('[data-testid="navbarLoginButton"]');
  await expect(account).toBeVisible();
  if (opts.loggedIn) await expect(page.locator('[data-testid="nav-link-admin"]')).toBeAttached();
  await expect(page.locator('[data-testid="nav-github-stars"]')).toHaveText(String(STAR_COUNT));
  await expect(page.locator('[data-testid="preview-login-admin"]')).toHaveCount(opts.preview ? 1 : 0);
  await page.evaluate(() => document.fonts.ready);
  return { context, page };
}

function measure(page: Page): Promise<Measurement> {
  return page.evaluate(() => {
    const nav = document.querySelector<HTMLElement>('[data-testid="nav-root"]')!;
    const navRect = nav.getBoundingClientRect();
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    };
    const items = Array.from(nav.querySelectorAll('a, button')).filter(
      (el) => visible(el) && !el.parentElement?.closest('a, button'),
    );
    const boxes = items.map((el) => {
      const r = el.getBoundingClientRect();
      const label =
        el.getAttribute('data-testid') ||
        el.getAttribute('aria-label') ||
        (el.textContent ?? '').trim().slice(0, 30) ||
        el.tagName;
      return { label, x: r.x, y: r.y, w: r.width, h: r.height };
    });
    const truncated = Array.from(nav.querySelectorAll<HTMLElement>('span'))
      .filter((el) => visible(el) && el.scrollWidth > el.clientWidth + 1)
      .map((el) => (el.textContent ?? '').trim());
    const overflowingGroups = Array.from(nav.children).filter(
      (el) => visible(el) && el.scrollWidth > el.clientWidth + 1,
    ).length;
    return {
      boxes,
      overflowingGroups,
      navLeft: navRect.left,
      navRight: navRect.right,
      truncated,
      pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
}

function problems(m: Measurement): string[] {
  const found: string[] = [];
  const eps = 0.5;
  for (let i = 0; i < m.boxes.length; i++) {
    const a = m.boxes[i];
    if (a.x < m.navLeft - eps || a.x + a.w > m.navRight + eps) {
      found.push(`"${a.label}" leaves the navbar`);
    }
    for (let j = i + 1; j < m.boxes.length; j++) {
      const b = m.boxes[j];
      const dx = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const dy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (dx > eps && dy > eps) found.push(`"${a.label}" overlaps "${b.label}" by ${dx.toFixed(1)}px`);
    }
  }
  for (const text of m.truncated) found.push(`label "${text}" is truncated`);
  if (m.overflowingGroups) found.push(`${m.overflowingGroups} navbar group(s) overflow their box`);
  if (m.pageOverflow) found.push('page scrolls horizontally');
  return found;
}

const SCENARIOS = [
  { loggedIn: false, preview: false, locale: 'en' },
  { loggedIn: false, preview: true, locale: 'en' },
  { loggedIn: true, preview: false, locale: 'en' },
  { loggedIn: true, preview: true, locale: 'en' },
  { loggedIn: true, preview: true, locale: 'es' },
] as const;

test.describe('Navbar width sweep (#252)', () => {
  for (const scenario of SCENARIOS) {
    const name = `${scenario.loggedIn ? 'logged-in' : 'logged-out'} ${
      scenario.preview ? 'with' : 'without'
    } preview logins (${scenario.locale})`;

    test(`no navbar items overlap: ${name}`, async ({ browser }) => {
      test.setTimeout(120_000);
      const { context, page } = await openNavbar(browser, scenario);
      const failures: string[] = [];
      for (const width of SWEEP) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(() => new Promise((r) => requestAnimationFrame(() => r(true))));
        if (SHOT_DIR && WIDTHS.includes(width)) {
          fs.mkdirSync(SHOT_DIR, { recursive: true });
          const file = `${name.replace(/[^a-z0-9]+/gi, '-')}-${width}.png`;
          await page.locator('[data-testid="nav-root"]').screenshot({ path: path.join(SHOT_DIR, file) });
        }
        for (const p of problems(await measure(page))) failures.push(`${width}px: ${p}`);
      }
      await context.close();
      expect(failures, failures.join('\n')).toEqual([]);
    });
  }
});
