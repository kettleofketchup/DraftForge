// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({
  ready: vi.fn(),
  authorize: vi.fn(),
  authenticate: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  construct: vi.fn(),
  patchUrlMappings: vi.fn(),
}));
vi.mock('~/components/api/axios', () => ({
  default: { get: mocks.get, post: mocks.post },
}));
vi.mock('@discord/embedded-app-sdk', () => ({
  patchUrlMappings: mocks.patchUrlMappings,
  DiscordSDK: class {
    instanceId = 'verified-instance';
    ready = mocks.ready;
    commands = { authorize: mocks.authorize, authenticate: mocks.authenticate };
    constructor(id: string) {
      mocks.construct(id);
    }
  },
}));
beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  window.history.replaceState(null, '', '/activity?frame_id=frame');
  mocks.get.mockResolvedValue({
    data: { enabled: true, client_id: 'runtime-app-id' },
  });
  mocks.authorize.mockResolvedValue({ code: 'oauth-code' });
  mocks.post.mockResolvedValue({
    data: {
      token: 'draft-token',
      kind: 'hero',
      draft_id: 7,
      user: { pk: 1 },
      access_token: 'oauth-access',
    },
  });
});
afterEach(() => vi.useRealTimers());
describe('Discord handshake', () => {
  it('uses runtime config, initializes once and keeps OAuth credentials out of returned session state', async () => {
    const { initializeDiscord } = await import('./discord');
    const first = initializeDiscord();
    expect(initializeDiscord()).toBe(first);
    const session = await first;
    expect(mocks.construct).toHaveBeenCalledExactlyOnceWith('runtime-app-id');
    expect(mocks.get).toHaveBeenCalledWith('/discord/activity/config/');
    expect(mocks.post).toHaveBeenCalledWith('/discord/activity/session/', {
      code: 'oauth-code',
      instance_id: 'verified-instance',
    });
    expect(mocks.authenticate).toHaveBeenCalledWith({
      access_token: 'oauth-access',
    });
    expect(session.token).toBe('draft-token');
    expect(session).not.toHaveProperty('access_token');
  });
  it('maps CDN image src attributes without replacing fetch or sockets', async () => {
    const { initializeDiscord, ACTIVITY_RESOURCE_MAPPINGS } =
      await import('./discord');
    await initializeDiscord();
    expect(mocks.patchUrlMappings).toHaveBeenCalledExactlyOnceWith(
      ACTIVITY_RESOURCE_MAPPINGS,
      {
        patchFetch: false,
        patchWebSocket: false,
        patchXhr: false,
        patchSrcAttributes: true,
      },
    );
    expect(
      ACTIVITY_RESOURCE_MAPPINGS.map((mapping) => mapping.target),
    ).toContain('cdn.cloudflare.steamstatic.com');
  });
  it('does not construct the SDK or fetch config on ordinary browser visits', async () => {
    window.history.replaceState(null, '', '/activity');
    const { initializeDiscord } = await import('./discord');
    await expect(initializeDiscord()).rejects.toThrow(
      'Launch DraftForge from Discord',
    );
    expect(mocks.construct).not.toHaveBeenCalled();
    expect(mocks.get).not.toHaveBeenCalled();
  });
  it('fails before SDK construction when the server disables Activities', async () => {
    mocks.get.mockResolvedValue({ data: { enabled: false, client_id: null } });
    const { initializeDiscord } = await import('./discord');
    await expect(initializeDiscord()).rejects.toThrow('unavailable');
    expect(mocks.construct).not.toHaveBeenCalled();
  });
  it('retries a rejected exchange without leaking another SDK message listener', async () => {
    mocks.post.mockRejectedValueOnce(new Error('rejected'));
    const { initializeDiscord } = await import('./discord');
    await expect(initializeDiscord()).rejects.toThrow('rejected');
    await expect(initializeDiscord()).resolves.toHaveProperty('draft_id', 7);
    expect(mocks.construct).toHaveBeenCalledOnce();
    expect(mocks.patchUrlMappings).toHaveBeenCalledOnce();
  });
  it('shares an in-progress handshake across StrictMode cleanup and remount', async () => {
    vi.useFakeTimers();
    const { initializeDiscord, releaseDiscordSession } =
      await import('./discord');
    const initial = initializeDiscord();
    releaseDiscordSession();
    expect(initializeDiscord()).toBe(initial);
    await vi.runAllTimersAsync();
    await initial;
    expect(mocks.post).toHaveBeenCalledOnce();
  });
  it('reauthenticates after a real route unmount without recreating the SDK', async () => {
    vi.useFakeTimers();
    const { initializeDiscord, releaseDiscordSession } =
      await import('./discord');
    await initializeDiscord();
    releaseDiscordSession();
    await vi.runAllTimersAsync();
    await initializeDiscord();
    expect(mocks.post).toHaveBeenCalledTimes(2);
    expect(mocks.construct).toHaveBeenCalledOnce();
  });
});
