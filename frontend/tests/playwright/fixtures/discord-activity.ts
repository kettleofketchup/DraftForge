/**
 * Discord Activity harness: a same-origin page that iframes /activity and
 * plays the Discord client's side of the embedded-app-sdk postMessage
 * protocol (handshake, READY, AUTHORIZE, AUTHENTICATE). The backend half is
 * POST /api/tests/discord-activity/setup/, which binds a voice channel to a
 * hero draft in "Activity Bracket Test" and registers a fake instance with
 * discordbot/activity_fake.py.
 */

import type { BrowserContext, FrameLocator, Page } from '@playwright/test';
import { API_URL, BASE_URL } from './base-url';

export const ACTIVITY_HARNESS_PATH = '/__activity_harness';

export interface DiscordActivitySetup {
  instance_id: string;
  guild_id: string;
  channel_id: string;
  code: string;
  discord_id: string;
  user_id: number;
  tournament_id: number;
  herodraft_id: number;
}

export interface HarnessCommand {
  cmd: string;
  args: unknown;
}

export async function setupDiscordActivity(
  context: BrowserContext,
): Promise<DiscordActivitySetup> {
  const resp = await context.request.post(
    `${API_URL}/tests/discord-activity/setup/`,
  );
  if (!resp.ok()) {
    throw new Error(
      `discord-activity setup failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return (await resp.json()) as DiscordActivitySetup;
}

function harnessHtml(setup: DiscordActivitySetup): string {
  const query = new URLSearchParams({
    frame_id: `e2e-frame-${setup.instance_id}`,
    instance_id: setup.instance_id,
    platform: 'desktop',
    guild_id: setup.guild_id,
    channel_id: setup.channel_id,
  });
  const config = JSON.stringify({
    src: `/activity?${query.toString()}`,
    code: setup.code,
    discordId: setup.discord_id,
  }).replace(/</g, '\\u003c');
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Activity harness</title>
<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>
</head>
<body>
<script>
const config = ${config};
const state = { commands: [] };
window.__activityHarness = state;
const frame = document.createElement('iframe');
frame.setAttribute('data-testid', 'activity-harness-frame');
const send = (payload) => frame.contentWindow.postMessage([1, payload], location.origin);
const handlers = {
  AUTHORIZE: () => ({ code: config.code }),
  AUTHENTICATE: (args) => ({
    access_token: args.access_token,
    user: { username: 'e2e', discriminator: '0', id: config.discordId, public_flags: 0 },
    scopes: ['identify'],
    expires: new Date(Date.now() + 3600000).toISOString(),
    application: { id: '0', name: 'DraftForge', description: '' },
  }),
  SUBSCRIBE: (_args, payload) => ({ evt: payload.evt }),
  UNSUBSCRIBE: (_args, payload) => ({ evt: payload.evt }),
};
window.addEventListener('message', (event) => {
  if (event.source !== frame.contentWindow || !Array.isArray(event.data)) return;
  const [opcode, payload] = event.data;
  if (opcode === 0) {
    send({ cmd: 'DISPATCH', evt: 'READY', nonce: null, data: { v: 1, config: { api_endpoint: '//discord.com/api', environment: 'production' } } });
    return;
  }
  if (opcode !== 1 || !payload || !payload.cmd) return;
  if (payload.cmd !== 'CAPTURE_LOG') state.commands.push({ cmd: payload.cmd, args: payload.args });
  const handler = handlers[payload.cmd];
  send({ cmd: payload.cmd, evt: null, nonce: payload.nonce, data: handler ? handler(payload.args || {}, payload) : null });
});
frame.src = config.src;
document.body.appendChild(frame);
</script>
</body>
</html>`;
}

/** Serve the harness on this slot's origin and open it; returns the Activity frame. */
export async function openActivityHarness(
  page: Page,
  setup: DiscordActivitySetup,
): Promise<FrameLocator> {
  await page.route(`${BASE_URL}${ACTIVITY_HARNESS_PATH}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: harnessHtml(setup),
    }),
  );
  await page.goto(`${BASE_URL}${ACTIVITY_HARNESS_PATH}`);
  return page.frameLocator('[data-testid="activity-harness-frame"]');
}

export async function harnessCommands(page: Page): Promise<HarnessCommand[]> {
  return page.evaluate(
    () =>
      (
        window as unknown as {
          __activityHarness: { commands: HarnessCommand[] };
        }
      ).__activityHarness.commands,
  );
}
