import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test';
import { loginAsUser, loginUser } from '../../fixtures/auth';
import { API_URL, BASE_URL } from '../../fixtures/base-url';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

/**
 * HeroDraft chat: per-team privacy, /all chat, and right-click suggestions.
 *
 * Uses the shared Real Tournament 38 draft via the drafting_phase key, which
 * resets the draft (and its chat) on every fetch.
 */

interface DraftTeamInfo {
  id: number;
  captain: { pk: number; username: string; discordId: string };
  team_name: string;
  is_first_pick: boolean | null;
  member_pks: number[];
}

interface DraftInfo {
  pk: number;
  draft_teams: DraftTeamInfo[];
}

interface Actor {
  context: BrowserContext;
  page: Page;
  draftPage: HeroDraftPage;
  frames: string[];
}

interface ChatFrame {
  type: string;
  viewer?: { role: string; team_id: number | null };
  messages?: Array<{ body: string; kind: string; hero_id: number | null }>;
  message?: { body: string; kind: string; hero_id: number | null };
}

const AVAILABLE_HERO = 1;
const DESKTOP = { width: 1440, height: 900 };
const BANNED_HERO = 2;

async function fetchDraft(context: BrowserContext): Promise<DraftInfo> {
  const res = await context.request.get(
    `${API_URL}/tests/herodraft-by-key/drafting_phase/`,
    { failOnStatusCode: false, timeout: 15000 },
  );
  if (!res.ok()) {
    throw new Error(
      `herodraft-by-key/drafting_phase failed: ${res.status()} ${await res.text()}`,
    );
  }
  return res.json();
}

async function newActor(
  browser: Browser,
  login: (context: BrowserContext) => Promise<unknown>,
  viewport = { width: 1280, height: 720 },
): Promise<Actor> {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport,
  });
  await login(context);
  const page = await context.newPage();
  const frames: string[] = [];
  page.on('websocket', (ws) => {
    ws.on('framereceived', (frame) => {
      frames.push(String(frame.payload));
    });
  });
  return { context, page, draftPage: new HeroDraftPage(page), frames };
}

async function openDraft(actor: Actor, draftPk: number): Promise<void> {
  await actor.page.goto(`${BASE_URL}/herodraft/${draftPk}`);
  await actor.draftPage.waitForModal();
  await actor.draftPage.waitForConnection(20000);
  await expect
    .poll(() => chatHistories(actor).length, { timeout: 15000 })
    .toBeGreaterThan(0);
}

function parsedFrames(actor: Actor): ChatFrame[] {
  const out: ChatFrame[] = [];
  for (const raw of actor.frames) {
    try {
      out.push(JSON.parse(raw));
    } catch {
      // non-JSON frames are irrelevant here
    }
  }
  return out;
}

function chatHistories(actor: Actor): ChatFrame[] {
  return parsedFrames(actor).filter((f) => f.type === 'chat_history');
}

function lastViewerRole(actor: Actor): string | undefined {
  return chatHistories(actor).at(-1)?.viewer?.role;
}

function expectNoFrameContains(actor: Actor, needle: string): void {
  const hits = actor.frames.filter((f) => f.includes(needle));
  expect(hits, `frames containing ${needle}`).toEqual([]);
}

function expectNoSuggestionFrames(actor: Actor): void {
  for (const frame of parsedFrames(actor)) {
    const messages = [
      ...(frame.messages ?? []),
      ...(frame.message ? [frame.message] : []),
    ];
    for (const m of messages) {
      expect(m.kind, `suggestion leaked in ${frame.type}`).toBe('text');
      expect(m.hero_id).toBeNull();
    }
  }
}

function chatInput(page: Page): Locator {
  return page.getByTestId('herodraft-chat-input');
}

function chatRows(page: Page): Locator {
  return page.locator('[data-testid^="herodraft-chat-message-"]');
}

function chatRow(page: Page, text: string): Locator {
  return chatRows(page).filter({ hasText: text });
}

async function openChatPanel(page: Page): Promise<void> {
  const panel = page.getByTestId('herodraft-chat-panel');
  if (await panel.isVisible()) return;
  await page.getByTestId('herodraft-chat-toggle').click();
  await expect(panel).toBeVisible();
}

async function sendChat(page: Page, text: string): Promise<void> {
  const input = chatInput(page);
  await expect(input).toBeEnabled({ timeout: 15000 });
  await input.fill(text);
  await expect(page.getByTestId('herodraft-chat-send')).toBeEnabled();
  await input.press('Enter');
  await expect(input).toHaveValue('');
}

async function rightClickHero(page: Page, heroId: number): Promise<void> {
  const hero = page.getByTestId(`herodraft-hero-${heroId}`);
  await hero.scrollIntoViewIfNeeded();
  const box = await hero.boundingBox();
  if (!box) throw new Error(`hero ${heroId} has no bounding box`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, {
    button: 'right',
  });
}

function sentinelFor(label: string): string {
  return `chat-${label}-${test.info().testId}-${Date.now()}`;
}

test.describe('@cicd HeroDraft chat', () => {
  let draft: DraftInfo;
  let teamA: DraftTeamInfo;
  let teamB: DraftTeamInfo;
  let memberAPk: number;
  let captainA: Actor;
  let memberA: Actor;
  let captainB: Actor;
  let spectator: Actor;
  const extraContexts: BrowserContext[] = [];

  async function setUp(
    browser: Browser,
    memberViewport?: { width: number; height: number },
  ): Promise<void> {
    const setupContext = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      draft = await fetchDraft(setupContext);
    } finally {
      await setupContext.close();
    }
    [teamA, teamB] = draft.draft_teams;
    const teamBUsers = new Set([teamB.captain.pk, ...teamB.member_pks]);
    const candidate = teamA.member_pks.find(
      (pk) => pk !== teamA.captain.pk && !teamBUsers.has(pk),
    );
    if (candidate === undefined) {
      throw new Error(`${teamA.team_name} has no non-captain member`);
    }
    memberAPk = candidate;

    captainA = await newActor(browser, (c) => loginAsUser(c, teamA.captain.pk));
    captainB = await newActor(browser, (c) => loginAsUser(c, teamB.captain.pk));
    memberA = await newActor(
      browser,
      (c) => loginAsUser(c, memberAPk),
      memberViewport,
    );
    spectator = await newActor(browser, loginUser);

    // Captains first: a drafting draft pauses if a connected captain has no
    // heartbeat once the tick loop starts.
    await openDraft(captainA, draft.pk);
    await openDraft(captainB, draft.pk);
    await openDraft(memberA, draft.pk);
    await openDraft(spectator, draft.pk);

    expect(lastViewerRole(captainA)).toBe('member');
    expect(lastViewerRole(memberA)).toBe('member');
    expect(lastViewerRole(captainB)).toBe('member');
    expect(lastViewerRole(spectator)).toBe('spectator');
  }

  test.afterEach(async ({ browser }) => {
    for (const actor of [captainA, memberA, captainB, spectator]) {
      await actor?.context.close().catch(() => {});
    }
    for (const context of extraContexts.splice(0)) {
      await context.close().catch(() => {});
    }
    if (!draft) return;
    // Wait for the server to process the captains' disconnects; a late one
    // landing after the next test's reset would pause the fresh draft.
    const probe = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await expect
        .poll(
          async () => {
            const res = await probe.request.get(
              `${API_URL}/herodraft/${draft.pk}/`,
            );
            const body: { draft_teams: Array<{ is_connected: boolean }> } =
              await res.json();
            return body.draft_teams.some((t) => t.is_connected);
          },
          { timeout: 15000 },
        )
        .toBe(false);
    } finally {
      await probe.close();
    }
  });

  /** Sends an all-chat line and waits until every listed actor has it. */
  async function allChatBarrier(
    sender: Actor,
    receivers: Actor[],
  ): Promise<void> {
    const barrier = sentinelFor('barrier');
    await sendChat(sender.page, `/all ${barrier}`);
    for (const r of receivers) {
      await expect
        .poll(() => r.frames.some((f) => f.includes(barrier)), {
          timeout: 15000,
        })
        .toBe(true);
    }
  }

  test('team message reaches only the sender team', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);
    const sentinel = sentinelFor('team');

    await openChatPanel(captainA.page);
    await sendChat(captainA.page, sentinel);

    await openChatPanel(memberA.page);
    await expect(chatRow(memberA.page, sentinel)).toHaveAttribute(
      'data-channel',
      'team',
    );
    await expect(chatRow(captainA.page, sentinel)).toBeVisible();

    await allChatBarrier(captainA, [captainB, spectator]);
    await openChatPanel(captainB.page);
    await openChatPanel(spectator.page);
    await expect(chatRow(captainB.page, sentinel)).toHaveCount(0);
    await expect(chatRow(spectator.page, sentinel)).toHaveCount(0);
    expectNoFrameContains(captainB, sentinel);
    expectNoFrameContains(spectator, sentinel);
  });

  test('/all message reaches everyone', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);
    const sentinel = sentinelFor('all');

    await openChatPanel(memberA.page);
    await sendChat(memberA.page, `/all glhf ${sentinel}`);

    for (const actor of [captainA, memberA, captainB, spectator]) {
      await openChatPanel(actor.page);
      await expect(chatRow(actor.page, sentinel)).toHaveAttribute(
        'data-channel',
        'all',
      );
    }
  });

  test('Enter opens chat and Escape closes it', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser, DESKTOP);
    const page = memberA.page;
    const panel = page.getByTestId('herodraft-chat-panel');
    const input = chatInput(page);

    await expect(input).toBeEnabled({ timeout: 15000 });
    await expect(page.getByTestId('herodraft-chat-enter-hint')).toBeVisible();
    await expect(panel).toBeHidden();

    await page.keyboard.press('Enter');
    await expect(panel).toBeVisible();
    await expect(input).toBeFocused();
    await expect(page.getByTestId('herodraft-chat-enter-hint')).toBeHidden();

    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(input).not.toBeFocused();

    await page.keyboard.press('Enter');
    await expect(input).toBeFocused();
    const sentinel = sentinelFor('enter');
    await page.keyboard.type(sentinel);
    await page.keyboard.press('Enter');
    await expect(input).toHaveValue('');
    await expect(chatRow(page, sentinel)).toBeVisible();
  });

  test('spectator composer is read-only', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);

    await expect(chatInput(spectator.page)).toBeDisabled();
    await expect(chatInput(spectator.page)).toHaveAttribute(
      'placeholder',
      /spectators/i,
    );
    await expect(
      spectator.page.getByTestId('herodraft-chat-send'),
    ).toBeDisabled();
    await expect(
      spectator.page
        .getByTestId('herodraft-bottom-toolbar')
        .getByText('Under Construction'),
    ).toHaveCount(0);
  });

  test('right-click suggestion stays on the team', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);

    await rightClickHero(memberA.page, AVAILABLE_HERO);
    const menu = memberA.page.getByTestId('herodraft-hero-suggest-menu');
    await expect(menu).toBeVisible();
    await memberA.page.getByTestId('herodraft-hero-suggest-ban').click();
    await expect(menu).toBeHidden();

    await openChatPanel(captainA.page);
    const suggestion = captainA.page.locator(
      `[data-testid^="herodraft-chat-message-"][data-kind="suggest_ban"][data-hero-id="${AVAILABLE_HERO}"]`,
    );
    await expect(suggestion).toHaveCount(1);
    await expect(
      suggestion.locator('[data-testid^="herodraft-chat-suggestion-"]'),
    ).toContainText('BAN');

    await allChatBarrier(memberA, [captainB, spectator]);
    for (const outsider of [captainB, spectator]) {
      await openChatPanel(outsider.page);
      await expect(
        outsider.page.locator(
          '[data-testid^="herodraft-chat-message-"][data-kind^="suggest_"]',
        ),
      ).toHaveCount(0);
      expectNoSuggestionFrames(outsider);
      expectNoFrameContains(outsider, 'suggest_');
    }
  });

  test('spectator right-click keeps the browser menu', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);

    await spectator.page.evaluate(() => {
      const w = window as Window & { __heroContextPrevented?: boolean[] };
      w.__heroContextPrevented = [];
      window.addEventListener('contextmenu', (e) => {
        w.__heroContextPrevented?.push(e.defaultPrevented);
      });
    });
    await rightClickHero(spectator.page, AVAILABLE_HERO);
    await expect(
      spectator.page.getByTestId('herodraft-hero-suggest-menu'),
    ).toHaveCount(0);
    const prevented = await spectator.page.evaluate(
      () =>
        (window as Window & { __heroContextPrevented?: boolean[] })
          .__heroContextPrevented,
    );
    expect(prevented).toEqual([false]);
  });

  test('suggest menu is disabled on a banned hero', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);

    const firstPick = teamA.is_first_pick ? captainA : captainB;
    await firstPick.draftPage.clickHero(BANNED_HERO);
    await firstPick.draftPage.confirmHeroSelection();
    await memberA.draftPage.assertHeroUnavailable(BANNED_HERO);

    await rightClickHero(memberA.page, BANNED_HERO);
    await expect(
      memberA.page.getByTestId('herodraft-hero-suggest-menu'),
    ).toBeVisible();
    for (const id of [
      'herodraft-hero-suggest-pick',
      'herodraft-hero-suggest-ban',
    ]) {
      await expect(memberA.page.getByTestId(id)).toHaveAttribute(
        'data-disabled',
        '',
      );
    }
  });

  test('reload restores team and all history', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser);
    const teamSentinel = sentinelFor('team');
    const allSentinel = sentinelFor('all');

    await openChatPanel(captainA.page);
    await sendChat(captainA.page, teamSentinel);
    await sendChat(captainA.page, `/all ${allSentinel}`);
    await expect(chatRow(captainA.page, allSentinel)).toBeVisible();

    memberA.frames.length = 0;
    await memberA.page.reload();
    await memberA.draftPage.waitForModal();
    await memberA.draftPage.waitForConnection(20000);
    await openChatPanel(memberA.page);
    await expect(chatRow(memberA.page, teamSentinel)).toHaveAttribute(
      'data-channel',
      'team',
    );
    await expect(chatRow(memberA.page, allSentinel)).toHaveAttribute(
      'data-channel',
      'all',
    );
  });

  test('history for outsiders never carries team chat', async ({ browser }) => {
    test.setTimeout(150000);
    await setUp(browser);
    const teamSentinel = sentinelFor('team');
    const allSentinel = sentinelFor('all');

    await openChatPanel(captainA.page);
    await sendChat(captainA.page, teamSentinel);
    await rightClickHero(memberA.page, AVAILABLE_HERO);
    await memberA.page.getByTestId('herodraft-hero-suggest-pick').click();
    await expect(
      captainA.page.locator(
        `[data-testid^="herodraft-chat-message-"][data-kind="suggest_pick"]`,
      ),
    ).toHaveCount(1);
    await sendChat(captainA.page, `/all ${allSentinel}`);
    await expect(chatRow(captainA.page, allSentinel)).toBeVisible();

    const anonContext = await browser.newContext({ ignoreHTTPSErrors: true });
    extraContexts.push(anonContext);
    const anonPage = await anonContext.newPage();
    const anon: Actor = {
      context: anonContext,
      page: anonPage,
      draftPage: new HeroDraftPage(anonPage),
      frames: [],
    };
    anonPage.on('websocket', (ws) => {
      ws.on('framereceived', (frame) => {
        anon.frames.push(String(frame.payload));
      });
    });

    captainB.frames.length = 0;
    spectator.frames.length = 0;
    await captainB.page.reload();
    await spectator.page.reload();
    await anonPage.goto(`${BASE_URL}/herodraft/${draft.pk}`);

    for (const outsider of [captainB, spectator, anon]) {
      await outsider.draftPage.waitForModal();
      await outsider.draftPage.waitForConnection(20000);
      await expect
        .poll(() => chatHistories(outsider).length, { timeout: 15000 })
        .toBeGreaterThan(0);
      const history = chatHistories(outsider).at(-1)!;
      expect(history.messages!.some((m) => m.body.includes(allSentinel))).toBe(
        true,
      );
      expectNoFrameContains(outsider, teamSentinel);
      expectNoFrameContains(outsider, 'suggest_');
      expectNoSuggestionFrames(outsider);

      await openChatPanel(outsider.page);
      await expect(chatRow(outsider.page, allSentinel)).toBeVisible();
      await expect(chatRow(outsider.page, teamSentinel)).toHaveCount(0);
      await expect(
        outsider.page.locator(
          '[data-testid^="herodraft-chat-message-"][data-kind^="suggest_"]',
        ),
      ).toHaveCount(0);
    }
    expect(lastViewerRole(anon)).toBe('spectator');
  });

  test('mobile sheet lets a member chat', async ({ browser }) => {
    test.setTimeout(120000);
    await setUp(browser, { width: 390, height: 844 });
    const sentinel = sentinelFor('mobile');

    await expect(memberA.page.getByTestId('herodraft-chat-input')).toHaveCount(
      0,
    );
    await memberA.page.getByTestId('herodraft-chat-toggle').click();
    await expect(
      memberA.page.getByTestId('herodraft-chat-sheet'),
    ).toBeVisible();
    await expect(chatInput(memberA.page)).toHaveCount(1);
    await expect(chatInput(memberA.page)).toBeFocused();
    await sendChat(memberA.page, sentinel);

    await openChatPanel(captainA.page);
    await expect(chatRow(captainA.page, sentinel)).toHaveAttribute(
      'data-channel',
      'team',
    );
  });

  test('chat works while paused and Resume stays clickable', async ({
    browser,
  }) => {
    test.setTimeout(120000);
    await setUp(browser);
    const sentinel = sentinelFor('paused');

    await captainA.page.getByTestId('herodraft-pause-btn').click();
    await memberA.draftPage.assertPaused();
    await captainA.draftPage.assertPaused();

    await openChatPanel(memberA.page);
    await sendChat(memberA.page, sentinel);

    await openChatPanel(captainA.page);
    await expect(chatRow(captainA.page, sentinel)).toHaveAttribute(
      'data-channel',
      'team',
    );

    const resume = captainA.page.getByTestId('herodraft-resume-btn');
    await expect(resume).toBeVisible();
    await expect(
      captainA.page.getByTestId('herodraft-chat-panel'),
    ).toBeVisible();
    const hitsResume = await resume.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(
        r.left + r.width / 2,
        r.top + r.height / 2,
      );
      return hit !== null && el.contains(hit);
    });
    expect(hitsResume).toBe(true);
  });

  test('closed chat previews team messages without blocking heroes', async ({
    browser,
  }) => {
    test.setTimeout(120000);
    await setUp(browser, DESKTOP);
    const sentinel = sentinelFor('preview');
    const page = memberA.page;
    const lines = page.getByTestId('herodraft-chat-preview-line');

    await rightClickHero(page, AVAILABLE_HERO);
    await page.getByTestId('herodraft-hero-suggest-pick').click();
    await expect(lines).toHaveCount(1);
    await sendChat(captainA.page, sentinel);
    await expect(lines).toHaveCount(2);
    await expect(lines.nth(1)).toContainText(sentinel);
    await expect(page.getByTestId('herodraft-chat-panel')).toHaveCount(0);

    const point = await page.evaluate(() => {
      const strip = document.querySelector(
        '[data-testid="herodraft-chat-preview"]',
      );
      if (!strip) return null;
      for (const line of strip.children) {
        const l = line.getBoundingClientRect();
        for (const hero of document.querySelectorAll<HTMLElement>(
          '[data-testid^="herodraft-hero-"][data-hero-id]',
        )) {
          const h = hero.getBoundingClientRect();
          const left = Math.max(l.left, h.left);
          const right = Math.min(l.right, h.right);
          const top = Math.max(l.top, h.top);
          const bottom = Math.min(l.bottom, h.bottom);
          if (right - left > 4 && bottom - top > 4) {
            const x = (left + right) / 2;
            const y = (top + bottom) / 2;
            const hit = document.elementFromPoint(x, y);
            return {
              x,
              y,
              heroId: hero.dataset.heroId,
              hitsHero: hit !== null && hero.contains(hit),
            };
          }
        }
      }
      return null;
    });
    expect(point, 'a hero sits under the preview strip').not.toBeNull();
    expect(point!.hitsHero).toBe(true);
    await page.mouse.click(point!.x, point!.y, { button: 'right' });
    await expect(page.getByTestId('herodraft-hero-suggest-menu')).toBeVisible();
  });

  test('open chat panel lets the grid scroll the Universal row above it', async ({
    browser,
  }) => {
    test.setTimeout(120000);
    await setUp(browser, DESKTOP);
    const page = memberA.page;

    // Stays under the 8-per-10s team limit even if an earlier test used it.
    await openChatPanel(captainA.page);
    for (let n = 0; n < 6; n++) {
      await sendChat(captainA.page, sentinelFor(`fill${n}`));
    }
    await openChatPanel(page);
    await expect(chatRows(page)).toHaveCount(6);

    const panel = page.getByTestId('herodraft-chat-panel');
    const list = page.getByTestId('herodraft-hero-list');
    const universal = page
      .getByTestId('herodraft-attr-grid-all')
      .locator('[data-hero-id]')
      .last();
    const panelTop = (await panel.boundingBox())!.y;
    await expect
      .poll(async () => {
        const box = (await universal.boundingBox())!;
        return box.y + box.height;
      })
      .toBeGreaterThan(panelTop);
    await expect
      .poll(() => list.evaluate((el) => el.scrollHeight - el.clientHeight))
      .toBeGreaterThan(0);

    await list.hover({ position: { x: 600, y: 50 } });
    await page.mouse.wheel(0, 2000);
    await expect
      .poll(async () => {
        const box = (await universal.boundingBox())!;
        return box.y + box.height;
      })
      .toBeLessThanOrEqual(panelTop);

    const box = (await universal.boundingBox())!;
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, {
      button: 'right',
    });
    await expect(page.getByTestId('herodraft-hero-suggest-menu')).toBeVisible();
    await expect(panel).toBeVisible();
  });

  test('logging out stops team delivery and clears the log', async ({
    browser,
  }) => {
    test.setTimeout(120000);
    await setUp(browser);
    const before = sentinelFor('before');
    const after = sentinelFor('after');

    await openChatPanel(captainA.page);
    await sendChat(captainA.page, before);
    await openChatPanel(memberA.page);
    await expect(chatRow(memberA.page, before)).toBeVisible();

    const res = await memberA.context.request.get(`${API_URL}/logout`, {
      maxRedirects: 0,
      failOnStatusCode: false,
    });
    expect(res.status()).toBeLessThan(400);

    memberA.frames.length = 0;
    await sendChat(captainA.page, after);
    await expect(chatRow(captainA.page, after)).toBeVisible();

    await expect
      .poll(() => lastViewerRole(memberA), { timeout: 15000 })
      .toBe('spectator');
    await allChatBarrier(captainA, [memberA]);
    expectNoFrameContains(memberA, after);

    await openChatPanel(memberA.page);
    await expect(chatRow(memberA.page, before)).toHaveCount(0);
    await expect(chatRow(memberA.page, after)).toHaveCount(0);
  });
});
