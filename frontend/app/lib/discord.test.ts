// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  ready: vi.fn(),
  authorize: vi.fn(),
  authenticate: vi.fn(),
  post: vi.fn(),
  construct: vi.fn(),
}));
vi.mock('~/components/api/axios', () => ({ default: { post: mocks.post } }));
vi.mock('@discord/embedded-app-sdk', () => ({
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
  vi.stubEnv('VITE_DISCORD_CLIENT_ID', 'app-id');
  window.history.replaceState(null, '', '/activity?frame_id=frame');
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
describe('Discord handshake', () => {
  it('initializes once, exchanges the code and keeps OAuth credentials out of returned session state', async () => {
    const { initializeDiscord } = await import('./discord');
    const first = initializeDiscord();
    const second = initializeDiscord();
    expect(first).toBe(second);
    const session = await first;
    expect(mocks.construct).toHaveBeenCalledOnce();
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
  it('does not construct the SDK on ordinary browser visits', async () => {
    window.history.replaceState(null, '', '/activity');
    const { initializeDiscord } = await import('./discord');
    await expect(initializeDiscord()).rejects.toThrow(
      'Launch DraftForge from Discord',
    );
    expect(mocks.construct).not.toHaveBeenCalled();
  });
  it('allows a retry after a rejected handshake', async () => {
    mocks.post.mockRejectedValueOnce(new Error('rejected'));
    const { initializeDiscord } = await import('./discord');
    await expect(initializeDiscord()).rejects.toThrow('rejected');
    await expect(initializeDiscord()).resolves.toHaveProperty('draft_id', 7);
    expect(mocks.construct).toHaveBeenCalledTimes(2);
  });
});
