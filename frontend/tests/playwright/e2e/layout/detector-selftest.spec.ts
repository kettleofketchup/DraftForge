import type { Page } from '@playwright/test';

import {
  clipEscapes,
  collisions,
  formatReports,
  loadKnownFindings,
  partitionFindings,
  prepareLayoutProbe,
  sweepLayout,
  sweepLayoutOnce,
  type KnownFinding,
} from '../../fixtures/layout';
import { test, expect, loginAdmin, visitAndWaitForHydration } from '../../fixtures';

/**
 * The layout detector's own regression tests. A detector that always returns [] looks exactly
 * like a working one, so each predicate gets a true positive and a correctly-clipped negative.
 * Every fixture has a shape guard (it really is in the failing shape) and a membership guard
 * (it really was measured) that fail rather than skip.
 *
 * No retries: a retry would hide an intermittently wrong predicate.
 */
test.describe.configure({ retries: 0 });

const V375 = { width: 375, height: 667 };

/** Two in-flow siblings that own text, the second pulled 30px over the first. */
const pair = (id: string): string =>
  `<p data-testid="${id}-upper" style="margin:0;height:40px;font:14px sans-serif">${id} upper line of text</p>` +
  `<p data-testid="${id}-lower" style="margin-top:-30px;height:40px;font:14px sans-serif">${id} lower line of text</p>`;

/**
 * Appends an absolutely positioned fixture to <body>, `offset` px below the navbar. Absolute so
 * the app shell can neither clip nor move it; only valid while the document is unscrolled.
 */
async function injectBelowNavbar(
  page: Page,
  spec: { id: string; offset: number; css: string; html: string },
): Promise<void> {
  await page.evaluate((s) => {
    const navBottom = document.querySelector('[data-testid=nav-root]')?.getBoundingClientRect().bottom ?? 0;
    const host = document.createElement('div');
    host.id = s.id;
    host.setAttribute('data-testid', s.id);
    host.style.cssText = `position:absolute;left:8px;top:${Math.round(navBottom) + s.offset}px;z-index:40;${s.css}`;
    host.innerHTML = s.html;
    document.body.appendChild(host);
  }, spec);
}

/** The probe's key() is `tag|testid|firstClass|domPath`. */
const keyPrefix = (tag: string, testid: string) => `${tag}|${testid}|`;

test.describe('layout detector self-test (@cicd)', () => {
  test.beforeEach(async ({ page, context }) => {
    await loginAdmin(context);
    await visitAndWaitForHydration(page, '/');
    await prepareLayoutProbe(page);
  });

  test('pairwise collision detector fires above the fold and below it', async ({ page }) => {
    const injected = await page.evaluate((html) => {
      const mk = (id: string, markup: string) => {
        const host = document.createElement('div');
        host.id = id;
        host.innerHTML = markup;
        return host;
      };
      const nav = document.querySelector('[data-testid=nav-root]');
      const anchor = nav?.parentElement ?? document.body;
      anchor.insertBefore(mk('selftest-above', html.above), nav?.nextElementSibling ?? null);

      // ~2000px down in a fixed-height overflow:visible holder that the pair overflows. Catches a
      // clip rect that picked up a viewport term or stopped at a padding box.
      const holder = document.createElement('div');
      holder.id = 'selftest-below-holder';
      holder.style.cssText = 'height:20px;overflow:visible;position:relative;margin-top:2000px';
      holder.appendChild(mk('selftest-below', html.below));
      document.body.appendChild(holder);

      const rectsOf = (id: string) =>
        [...document.querySelectorAll(`#${id} p`)]
          .map((p) => p.getBoundingClientRect())
          .map((r) => ({ top: r.top, bottom: r.bottom }));
      const holderRect = holder.getBoundingClientRect();
      const lowerRect = document.querySelector('[data-testid=selftest-below-lower]')!.getBoundingClientRect();
      return {
        above: rectsOf('selftest-above'),
        below: rectsOf('selftest-below'),
        belowOverflowsHolder: lowerRect.bottom > holderRect.bottom,
        belowTop: lowerRect.top,
        viewportH: window.innerHeight,
      };
    }, { above: pair('selftest-above'), below: pair('selftest-below') });

    for (const name of ['above', 'below'] as const) {
      const p = injected[name];
      expect(p.length, `${name}: both paragraphs must render`).toBe(2);
      expect(p[1].top, `${name}: the second paragraph must be pulled over the first`).toBeLessThan(p[0].bottom);
    }
    expect(injected.belowTop, 'the below-fold fixture must be off-screen').toBeGreaterThan(injected.viewportH);
    expect(injected.belowOverflowsHolder, 'the below-fold fixture must overflow its holder').toBe(true);

    const pop = await sweepLayoutOnce(page, { debugKeys: true });
    for (const id of ['selftest-above', 'selftest-below']) {
      expect(
        pop.debugKeys!.candidates.some((k) => k.startsWith(keyPrefix('p', `${id}-upper`))),
        `${id} must be in the measured candidate population`,
      ).toBe(true);
    }

    const hits = await collisions(page);
    const above = hits.filter((h) => /selftest-above/.test(`${h.a}${h.b}`));
    const below = hits.filter((h) => /selftest-below/.test(`${h.a}${h.b}`));
    expect(above.length, 'an overlapping pair above the fold must be reported').toBeGreaterThan(0);
    expect(
      below.length,
      'an overlapping pair ~2000px below the fold must be reported; empty means the clip rect ' +
        'has picked up a viewport term',
    ).toBeGreaterThan(0);
    expect(above[0].keyA, 'Collision keys must be text-free').not.toMatch(/upper line/);
    expect(above[0].keyA, 'the key must not collapse to a bare tag name').not.toBe('p');
  });

  test('a wrapped inline row is not reported as overlapping', async ({ page }) => {
    // getBoundingClientRect() on a wrapped inline is the union of its line boxes and swallows its
    // neighbours; the detector must use getClientRects().
    await page.evaluate(() => {
      const host = document.createElement('div');
      host.id = 'overlap-selftest';
      host.style.cssText = 'width:150px;font:14px sans-serif;';
      host.innerHTML =
        '<div><span data-testid="wrap-selftest-1">Tournament: Spring Inhouse League</span> ' +
        '<span data-testid="wrap-selftest-2">|</span> ' +
        '<span data-testid="wrap-selftest-3">Format: double elim</span> ' +
        '<span data-testid="wrap-selftest-4">|</span> ' +
        '<span data-testid="wrap-selftest-5">Captain: a-very-long-player-name</span></div>';
      document.body.appendChild(host);
    });

    const lineCount = await page.evaluate(() => {
      const spans = [...document.querySelectorAll('#overlap-selftest span')];
      return Math.max(...spans.map((s) => s.getClientRects().length));
    });
    expect(lineCount, 'a span must break across lines for this to be a real test').toBeGreaterThan(1);

    const pop = await sweepLayoutOnce(page, { debugKeys: true });
    const spanKeys = pop.debugKeys!.candidates.filter((k) => k.startsWith('span|wrap-selftest-'));
    expect(spanKeys.length, 'the injected spans must be pairwise candidates').toBeGreaterThan(1);

    const hits = await collisions(page);
    const injected = hits.filter((h) => /wrap-selftest-/.test(`${h.a}${h.b}`));
    expect(injected, `wrapped inline text reported as overlapping:\n${JSON.stringify(injected, null, 2)}`).toEqual([]);
  });

  test('the stability window drops a finding that does not survive re-measure', async ({ page }) => {
    // The pair separates on the rAF after the detector's first read, i.e. before the re-measure.
    await page.evaluate((html) => {
      const host = document.createElement('div');
      host.id = 'flicker-selftest';
      host.innerHTML = html;
      (document.querySelector('[data-testid=nav-root]')?.parentElement ?? document.body).appendChild(host);
      const lower = document.querySelector('[data-testid=flicker-selftest-lower]') as HTMLElement;
      const original = lower.getClientRects.bind(lower);
      let reads = 0;
      lower.getClientRects = function patched() {
        const rects = original();
        if (++reads === 1) requestAnimationFrame(() => { lower.style.marginTop = '0px'; });
        return rects;
      };
    }, pair('flicker-selftest'));

    const report = await sweepLayoutOnce(page, { debugKeys: true });
    const base = report.findings.find((f) => f.state === 'base');
    expect(
      (base?.collisions ?? []).filter((c) => /flicker-selftest/.test(`${c.a}${c.b}`)),
      'a pair that separates before the re-measure must not survive the stability window',
    ).toEqual([]);
    expect(
      report.states.find((s) => s.state === 'base')?.restabilised,
      'the base state must have run the re-measure, or this test is vacuous',
    ).toBe(true);
  });

  test('clip-escape detector fires on an injected clip host', async ({ page }) => {
    // E overflows an 80px overflow:hidden host (a correctly clipped negative on its own). F, a
    // position:fixed descendant laid over the escaped strip, really paints there.
    await injectBelowNavbar(page, {
      id: 'escape-host',
      offset: 24,
      css: 'width:240px;height:80px;overflow:hidden;background:#fff',
      html:
        '<div data-testid="escape-selftest" style="height:320px;background:#c00;color:#fff;font:14px sans-serif">' +
        'escape-selftest painted content' +
        '<span data-testid="escape-selftest-paint" style="position:fixed;background:#0a0;z-index:99999"></span></div>',
    });

    const shape = await page.evaluate(() => {
      const navBottom = document.querySelector('[data-testid=nav-root]')?.getBoundingClientRect().bottom ?? 0;
      const hostRect = document.querySelector('[data-testid=escape-host]')!.getBoundingClientRect();
      const elRect = document.querySelector('[data-testid=escape-selftest]')!.getBoundingClientRect();
      const paint = document.querySelector('[data-testid=escape-selftest-paint]') as HTMLElement;
      paint.style.left = `${Math.round(hostRect.left)}px`;
      paint.style.top = `${Math.round(hostRect.bottom)}px`;
      paint.style.width = `${Math.round(hostRect.width)}px`;
      paint.style.height = `${Math.round(elRect.bottom - hostRect.bottom)}px`;
      const strip = paint.getBoundingClientRect();
      const cx = strip.left + strip.width / 2;
      const cy = strip.top + strip.height / 2;
      const hit = document.elementFromPoint(cx, cy) as HTMLElement | null;
      return {
        escapedBy: Math.round(elRect.bottom - hostRect.bottom),
        clips: getComputedStyle(document.querySelector('[data-testid=escape-host]')!).overflowY,
        centroidInViewport: cx > 0 && cx < window.innerWidth && cy > 0 && cy < window.innerHeight,
        centroidBelowNavbar: cy > navBottom,
        hitTestid: hit?.getAttribute('data-testid') ?? null,
      };
    });

    expect(shape.clips, 'the host must actually clip').toBe('hidden');
    expect(shape.escapedBy, 'E must overflow the host by more than the escape floor').toBeGreaterThan(200);
    expect(shape.centroidInViewport, 'the probe point must be inside the viewport').toBe(true);
    expect(shape.centroidBelowNavbar, 'the probe point must be below the navbar band').toBe(true);
    expect(shape.hitTestid, 'the fixture must genuinely paint in the escaped strip').toBe('escape-selftest-paint');

    const pop = await sweepLayoutOnce(page, { debugKeys: true });
    expect(
      pop.debugKeys!.geometricEscapes.some((k) => k.startsWith(keyPrefix('div', 'escape-selftest'))),
      'the fixture must be in the measured geometric-escape population',
    ).toBe(true);

    const escapes = await clipEscapes(page);
    const mine = escapes.filter((e) => e.elKey.startsWith(keyPrefix('div', 'escape-selftest')));
    expect(
      mine.length,
      `content painted outside its clip host must be reported:\n${JSON.stringify(escapes, null, 2)}`,
    ).toBeGreaterThan(0);
    expect(['self', 'descendant'], `unexpected via: ${mine[0].via}`).toContain(mine[0].via);
  });

  test('clip-escape reports through a pointer-events:none ancestor', async ({ page }) => {
    // shadcn primitives put pointer-events:none on their svgs, so the hit resolves to the
    // painting ancestor rather than the escaping icon itself.
    await injectBelowNavbar(page, {
      id: 'pe-host',
      offset: 24,
      css: 'width:260px;height:120px;background:#eee',
      html:
        '<div data-testid="pe-clip" style="overflow:hidden;width:40px;height:40px;margin:20px;pointer-events:none">' +
        '<svg data-testid="pe-escape" width="200" height="40" viewBox="0 0 200 40" style="pointer-events:none">' +
        '<rect width="200" height="40" fill="#06c"></rect></svg></div>',
    });

    const shape = await page.evaluate(() => {
      const navBottom = document.querySelector('[data-testid=nav-root]')?.getBoundingClientRect().bottom ?? 0;
      const clip = document.querySelector('[data-testid=pe-clip]')!.getBoundingClientRect();
      const svg = document.querySelector('[data-testid=pe-escape]')!.getBoundingClientRect();
      const px = clip.right + (svg.right - clip.right) / 2;
      const py = clip.top + clip.height / 2;
      const hit = document.elementFromPoint(px, py) as HTMLElement | null;
      return {
        escapedWidth: Math.round(svg.right - clip.right),
        probeInViewport: px > 0 && px < window.innerWidth && py > navBottom && py < window.innerHeight,
        hitTestid: hit?.getAttribute('data-testid') ?? null,
      };
    });

    expect(shape.escapedWidth, 'the svg must overflow its clip box').toBeGreaterThan(120);
    expect(shape.probeInViewport, 'the probe point must be inside the viewport, below the navbar').toBe(true);
    expect(shape.hitTestid, 'elementFromPoint must resolve to the pointer-events:auto ancestor').toBe('pe-host');

    const pop = await sweepLayoutOnce(page, { debugKeys: true });
    expect(
      pop.debugKeys!.geometricEscapes.some((k) => k.startsWith(keyPrefix('svg', 'pe-escape'))),
      'the svg must be in the measured geometric-escape population',
    ).toBe(true);

    const escapes = await clipEscapes(page);
    const mine = escapes.filter((e) => e.elKey.startsWith(keyPrefix('svg', 'pe-escape')));
    expect(mine.length, 'an escaping icon under a pointer-events:none chain must be reported').toBeGreaterThan(0);
    expect(mine[0].via).toBe('pointer-events-none-ancestor');
  });

  test('clip-escape stays quiet on four correctly-clipped shapes', async ({ page }) => {
    // A: in-flow, clipped horizontally.
    await injectBelowNavbar(page, {
      id: 'negative-a-host',
      offset: 24,
      css: 'width:200px;height:40px;overflow:hidden',
      html:
        '<div data-testid="negative-a" style="width:600px;height:40px;background:#0a0;color:#fff;font:14px sans-serif">' +
        'negative-a in-flow horizontal overflow</div>',
    });

    // B: scrolled out of view -- escape geometry with no paint.
    await injectBelowNavbar(page, {
      id: 'negative-b-host',
      offset: 88,
      css: 'width:200px;height:60px;overflow-y:auto',
      html:
        '<div data-testid="negative-b" style="height:120px;background:#06c;color:#fff;font:14px sans-serif">' +
        'negative-b scrolled out of view</div>' +
        '<div style="height:240px">filler</div>',
    });

    // C: a position:fixed host and its static child, neither clipped by the overflow ancestor.
    await injectBelowNavbar(page, {
      id: 'negative-c-host',
      offset: 164,
      css: 'width:200px;height:40px;overflow:hidden',
      html:
        '<div data-testid="negative-c-fixed" style="position:fixed;left:8px;bottom:24px;width:200px;height:60px;' +
        'background:#909;color:#fff;font:14px sans-serif">' +
        '<span data-testid="negative-c-child">negative-c static child of a fixed host</span></div>',
    });

    // D: a shrink-wrapping display:table wrapper (as Radix ScrollArea renders) that paints nothing.
    await injectBelowNavbar(page, {
      id: 'negative-d-host',
      offset: 216,
      css: 'width:200px;height:40px;overflow:hidden',
      html:
        '<div data-testid="negative-d" style="min-width:100%;display:table">' +
        '<span style="white-space:nowrap;font:14px sans-serif">negative-d a very long shrink-wrapping row of text</span>' +
        '</div>',
    });

    const shape = await page.evaluate(() => {
      const rect = (sel: string) => document.querySelector(sel)!.getBoundingClientRect();
      const b = document.querySelector('[data-testid=negative-b-host]') as HTMLElement;
      b.scrollTop = 180;
      const dHost = rect('[data-testid=negative-d-host]');
      const d = rect('[data-testid=negative-d]');
      const bChild = rect('[data-testid=negative-b]');
      return {
        aOverflows: rect('[data-testid=negative-a]').right > rect('[data-testid=negative-a-host]').right,
        bScrolledOut: bChild.bottom < rect('[data-testid=negative-b-host]').top,
        cIsFixed: getComputedStyle(document.querySelector('[data-testid=negative-c-fixed]')!).position,
        dOverflows: d.right > dHost.right,
      };
    });

    expect(shape.aOverflows, 'A must overflow its clip host horizontally').toBe(true);
    expect(shape.bScrolledOut, 'B must be scrolled entirely above its clip rect').toBe(true);
    expect(shape.cIsFixed, 'C must be position:fixed').toBe('fixed');
    expect(shape.dOverflows, 'D must shrink-wrap wider than its clip host').toBe(true);

    const pop = await sweepLayoutOnce(page, { debugKeys: true });
    expect(
      pop.debugKeys!.geometricEscapes.some((k) => k.startsWith(keyPrefix('div', 'negative-d'))),
      'D must reach the escape pass, or its absence says nothing about the paintability check',
    ).toBe(true);

    const escapes = await clipEscapes(page);
    for (const [fixture, why] of [
      ['negative-a', 'an in-flow box clipped horizontally is not an escape'],
      ['negative-b', 'a box scrolled out of view has escape geometry but no paint'],
      ['negative-c-fixed', 'a fixed host escaping a clip box is CSS-correct'],
      ['negative-c-child', 'a static child of a fixed host is clipped by nothing above the host'],
      ['negative-d', 'a wrapper with no background, border or text paints nothing'],
    ] as const) {
      expect(
        escapes.filter((e) => e.elKey.includes(`|${fixture}|`)),
        `${fixture}: ${why}\n${JSON.stringify(escapes, null, 2)}`,
      ).toEqual([]);
    }
  });

  test('a sub-2px sliver past a clip edge is not an escape', async ({ page }) => {
    // 300x1 clears the area floor; only the thickness rule keeps it out.
    await injectBelowNavbar(page, {
      id: 'sliver-host',
      offset: 24,
      css: 'width:300px;height:40px;overflow:hidden',
      html: '<div data-testid="sliver-negative" style="margin-top:-1px;height:41px;background:#06c"></div>',
    });

    const escapedBy = await page.evaluate(() => {
      const host = document.querySelector('[data-testid=sliver-host]')!.getBoundingClientRect();
      const el = document.querySelector('[data-testid=sliver-negative]')!.getBoundingClientRect();
      return { top: host.top - el.top, width: el.width };
    });
    expect(escapedBy.top, 'the fixture must poke 1px above its clip host').toBeCloseTo(1, 1);
    expect(escapedBy.width * escapedBy.top, 'the sliver must clear the area floor').toBeGreaterThanOrEqual(256);

    const report = await sweepLayoutOnce(page, { debugKeys: true });
    expect(
      report.debugKeys!.geometricEscapes.filter((k) => k.startsWith(keyPrefix('div', 'sliver-negative'))),
      'a 1px sliver must not reach the escape pass',
    ).toEqual([]);
  });

  test('unprobeable strips are counted, and the navbar band is resolved by layout', async ({ page }) => {
    // An escaped strip entirely past the right viewport edge.
    await injectBelowNavbar(page, {
      id: 'offscreen-host',
      offset: 24,
      css: 'left:calc(100vw - 10px);width:10px;height:40px;overflow:hidden',
      html:
        '<div data-testid="offscreen-negative" style="width:600px;height:40px;background:#06c;color:#fff;' +
        'font:14px sans-serif">offscreen strip</div>',
    });

    // An escaped strip entirely inside the navbar band.
    await injectBelowNavbar(page, {
      id: 'navbar-host',
      offset: -4,
      css: 'width:200px;height:40px;overflow:hidden',
      html:
        '<div data-testid="navbar-negative" style="margin-top:-44px;height:44px;background:#c60;color:#fff;' +
        'font:14px sans-serif">above the navbar</div>',
    });

    const shape = await page.evaluate(() => {
      const navBottom = document.querySelector('[data-testid=nav-root]')?.getBoundingClientRect().bottom ?? 0;
      const off = document.querySelector('[data-testid=offscreen-negative]')!.getBoundingClientRect();
      const offHost = document.querySelector('[data-testid=offscreen-host]')!.getBoundingClientRect();
      const nav = document.querySelector('[data-testid=navbar-negative]')!.getBoundingClientRect();
      const navHost = document.querySelector('[data-testid=navbar-host]')!.getBoundingClientRect();
      return {
        navBottom,
        offStripStartsOffscreen: offHost.right >= window.innerWidth - 1 && off.right > window.innerWidth,
        navStripAboveBand: nav.bottom <= navHost.top && nav.bottom <= navBottom && nav.top > 0,
      };
    });

    expect(shape.offStripStartsOffscreen, 'the off-screen fixture must escape past the viewport edge').toBe(true);
    expect(shape.navStripAboveBand, 'the navbar fixture must escape entirely into the navbar band').toBe(true);

    const report = await sweepLayoutOnce(page, { debugKeys: true });
    for (const fixture of ['offscreen-negative', 'navbar-negative']) {
      expect(
        report.debugKeys!.geometricEscapes.some((k) => k.startsWith(keyPrefix('div', fixture))),
        `${fixture} must be in the measured geometric-escape population`,
      ).toBe(true);
    }
    expect(report.ledger.unprobeable, 'both fixtures must be counted unprobeable').toBeGreaterThanOrEqual(2);
    expect(
      report.findings.flatMap((f) => f.escapes).filter((e) => /offscreen-negative|navbar-negative/.test(e.elKey)),
      'an unprobeable strip must not be reported as a finding',
    ).toEqual([]);
    expect(
      report.ledger.navbarHeightPx,
      'navbarHeightPx must be the navbar bottom measured by layout',
    ).toBe(Math.round(shape.navBottom));
    expect(report.ledger.navbarHeightPx, 'the navbar must have a real height').toBeGreaterThanOrEqual(48);
  });

  test('the scroll walk re-measures, and the clip filter keeps it honest', async ({ page }) => {
    const shape = await page.evaluate((html) => {
      const container = document.createElement('div');
      container.id = 'scroll-selftest-host';
      container.setAttribute('data-testid', 'scroll-selftest-host');
      // Taller than any route content so the walk probes it first.
      container.style.cssText = 'height:120px;overflow-y:auto;position:static';
      const inner = document.createElement('div');
      inner.style.cssText = 'height:100000px;position:relative';
      const host = document.createElement('div');
      host.id = 'scroll-selftest';
      host.style.cssText = 'position:absolute;bottom:20px;left:0;right:0';
      host.innerHTML = html;
      inner.appendChild(host);
      container.appendChild(inner);
      (document.querySelector('[data-testid=nav-root]')?.parentElement ?? document.body).appendChild(container);

      const clip = container.getBoundingClientRect();
      const at0 = host.getBoundingClientRect();
      container.scrollTop = container.scrollHeight - container.clientHeight;
      const atMax = host.getBoundingClientRect();
      container.scrollTop = 0;
      return {
        scrollable: container.scrollHeight - container.clientHeight > 8,
        outsideAt0: at0.top >= clip.bottom,
        insideAtMax: atMax.top < clip.bottom && atMax.bottom > clip.top,
      };
    }, pair('scroll-selftest'));

    expect(shape.scrollable, 'the injected container must actually scroll').toBe(true);
    expect(shape.outsideAt0, 'at scrollTop=0 the pair must be outside the clip rect').toBe(true);
    expect(shape.insideAtMax, 'at scrollTop=max the pair must be inside the clip rect').toBe(true);

    const [report] = await sweepLayout(page, {
      viewports: [V375],
      states: ['scroll'],
      scrollFractions: [1],
      maxScrollContainers: 1,
    });

    expect(
      report.ledger.statesExercised,
      'the injected container must be the one probed',
    ).toContain('scroll:scroll-selftest-host@1');

    const forState = (pred: (s: string) => boolean) =>
      report.findings.filter((f) => pred(f.state)).flatMap((f) => f.collisions)
        .filter((c) => /scroll-selftest/.test(`${c.a}${c.b}`));

    expect(forState((s) => s === 'base'), 'the clip filter must drop a pair outside its container').toEqual([]);
    expect(
      forState((s) => s === 'scroll:scroll-selftest-host@1').length,
      'the scroll walk must report the pair once it is inside the clip rect',
    ).toBeGreaterThan(0);

    const restored = await page.evaluate(
      () => (document.getElementById('scroll-selftest-host') as HTMLElement).scrollTop === 0,
    );
    expect(restored, 'every scrolled container must be restored').toBe(true);
  });

  /** Injects the standard pair and returns the report plus a quarantine entry naming its finding. */
  async function quarantineFixture(page: Page) {
    await page.evaluate((html) => {
      const host = document.createElement('div');
      host.id = 'quarantine-selftest';
      host.innerHTML = html;
      (document.querySelector('[data-testid=nav-root]')?.parentElement ?? document.body).appendChild(host);
    }, pair('quarantine-selftest'));

    const report = await sweepLayoutOnce(page);
    const mine = (report.findings.find((f) => f.state === 'base')?.collisions ?? []).filter((c) =>
      /quarantine-selftest/.test(`${c.a}${c.b}`),
    );
    expect(mine.length, 'the fixture must be reported before it can be quarantined').toBeGreaterThan(0);

    const entry: KnownFinding = {
      route: '/',
      viewport: `${report.viewport.width}x${report.viewport.height}`,
      state: 'base',
      kind: 'collision',
      findingKey: `${mine[0].keyA} ${mine[0].keyB}`,
      owner: 'layout-selftest',
      issue: 'LAYOUT-SELFTEST',
      note: 'injected by detector-selftest.spec.ts',
      added: '2026-11-12',
    };
    return { report, entry };
  }

  test('a quarantined finding does not gate, and is still reported', async ({ page }) => {
    const { report, entry } = await quarantineFixture(page);

    const { fresh, matched, stale } = partitionFindings([report], '/', [entry]);
    expect(matched, 'the entry must match the finding it names').toEqual([entry]);
    expect(fresh.filter((f) => f.findingKey === entry.findingKey), 'a quarantined finding must not gate').toEqual([]);
    expect(stale, 'an entry that fired is not stale').toEqual([]);

    const rendered = formatReports([report], matched);
    expect(rendered, 'the quarantined finding must still be named in the report').toContain('LAYOUT-SELFTEST');
  });

  test('a stale quarantine entry is reported, and intermittent exempts it', async ({ page }) => {
    const { report } = await quarantineFixture(page);

    const bogus: KnownFinding = {
      route: '/',
      viewport: `${report.viewport.width}x${report.viewport.height}`,
      state: 'base',
      kind: 'collision',
      findingKey: 'p|nothing-fires-here|| 9.9.9 p|nothing-fires-here-either|| 9.9.8',
      owner: 'layout-selftest',
      issue: 'LAYOUT-SELFTEST-STALE',
      note: 'injected by detector-selftest.spec.ts',
      added: '2026-11-12',
    };
    expect(partitionFindings([report], '/', [bogus]).stale, 'a key that stopped firing is stale').toEqual([bogus]);

    const intermittent: KnownFinding = { ...bogus, intermittent: true };
    expect(
      partitionFindings([report], '/', [intermittent]).stale,
      'intermittent:true is the only exemption from the stale check',
    ).toEqual([]);
  });

  test('the quarantine matches exactly, and the checked-in file loads', async ({ page }) => {
    const { report, entry } = await quarantineFixture(page);

    const mutations: Array<[string, KnownFinding]> = [
      ['route', { ...entry, route: '/tournaments' }],
      ['viewport', { ...entry, viewport: '1440x900' }],
      ['state', { ...entry, state: 'scroll:outlet_root@1' }],
      ['kind', { ...entry, kind: 'escape' }],
      ['findingKey', { ...entry, findingKey: `${entry.findingKey} extra` }],
    ];
    for (const [field, mutated] of mutations) {
      const { fresh, matched } = partitionFindings([report], '/', [mutated]);
      expect(matched, `an entry differing in \`${field}\` must not quarantine anything`).toEqual([]);
      expect(
        fresh.some((f) => f.findingKey === entry.findingKey),
        `an entry differing in \`${field}\` must leave the finding gating`,
      ).toBe(true);
    }

    expect(() => loadKnownFindings(), 'the checked-in quarantine must parse and validate').not.toThrow();
  });
});
