// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  setActivityCredential,
  setActivityRefresher,
  type ActivityCredential,
} from '~/lib/activity-session';
import {
  ACTIVITY_OUT_OF_SCOPE,
  ACTIVITY_SESSION_ENDED,
  getWebSocketManager,
} from './WebSocketManager';
import type { ConnectionState } from './types';

class FakeSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  constructor(
    public url: string,
    public protocols?: string[],
  ) {
    FakeSocket.instances.push(this);
  }
  send() {}
  close() {}
  serverClose(code: number) {
    this.readyState = 3;
    this.onclose?.({ code, reason: '' });
  }
}

const heroCredential = (token: string): ActivityCredential => ({
  token,
  scope: 'draft',
  tournament_id: null,
  pin: { kind: 'hero', id: 7 },
  site_url: 'https://site.test',
});

const tournamentCredential = (token: string): ActivityCredential => ({
  token,
  scope: 'tournament',
  tournament_id: 5,
  pin: null,
  site_url: 'https://site.test',
});

const flush = async () => {
  await vi.runAllTimersAsync();
};

beforeEach(() => {
  vi.useFakeTimers();
  FakeSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeSocket);
  setActivityCredential(heroCredential('old-token'));
});
afterEach(() => {
  getWebSocketManager().disconnectAll();
  setActivityRefresher(null);
  setActivityCredential(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('Activity sockets', () => {
  it('re-runs the Discord handshake on 4401 and reconnects with the new token', async () => {
    const refresher = vi.fn(async () => {
      setActivityCredential(heroCredential('new-token'));
    });
    setActivityRefresher(refresher);
    const manager = getWebSocketManager();
    manager.connect(`wss://${window.location.host}/api/herodraft/7/`);
    await flush();
    const first = FakeSocket.instances.at(-1)!;
    expect(first.url).toContain('/api/discord/activity/draft/7/');
    expect(first.protocols).toEqual(['draftactivity', 'old-token']);

    first.serverClose(4401);
    await flush();

    expect(refresher).toHaveBeenCalledOnce();
    expect(FakeSocket.instances.at(-1)!.protocols).toEqual([
      'draftactivity',
      'new-token',
    ]);
  });

  it('stops retrying a rejected credential when the handshake fails', async () => {
    const states: string[] = [];
    setActivityRefresher(() => Promise.reject(new Error('unlinked')));
    getWebSocketManager().connect(
      `wss://${window.location.host}/api/herodraft/7/`,
      { onStateChange: (state) => states.push(state.status) },
    );
    await flush();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    expect(FakeSocket.instances).toHaveLength(1);
    expect(states.at(-1)).toBe('disconnected');
  });
});

describe('Activity sockets with a tournament credential', () => {
  const connect99 = async () => {
    const states: ConnectionState[] = [];
    getWebSocketManager().connect(
      `wss://${window.location.host}/api/herodraft/99/`,
      { onStateChange: (state) => states.push(state) },
    );
    await flush();
    return states;
  };

  beforeEach(() => {
    setActivityCredential(tournamentCredential('old-token'));
  });

  it('opens the Activity socket for any draft id in the tournament', async () => {
    await connect99();
    const socket = FakeSocket.instances.at(-1)!;
    expect(socket.url).toContain('/api/discord/activity/draft/99/');
    expect(socket.protocols).toEqual(['draftactivity', 'old-token']);
  });

  it('reconnects the same draft with the refreshed token on 4401', async () => {
    const refresher = vi.fn(async () => {
      setActivityCredential(tournamentCredential('new-token'));
    });
    setActivityRefresher(refresher);
    await connect99();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    expect(refresher).toHaveBeenCalledOnce();
    const socket = FakeSocket.instances.at(-1)!;
    expect(FakeSocket.instances).toHaveLength(2);
    expect(socket.url).toContain('/api/discord/activity/draft/99/');
    expect(socket.protocols).toEqual(['draftactivity', 'new-token']);
  });

  it('refreshes only once when the refreshed credential is rejected again', async () => {
    const refresher = vi.fn(async () => {
      setActivityCredential(tournamentCredential('new-token'));
    });
    setActivityRefresher(refresher);
    const states = await connect99();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    vi.advanceTimersByTime(60_000);
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    expect(refresher).toHaveBeenCalledOnce();
    expect(FakeSocket.instances).toHaveLength(2);
    expect(states.at(-1)).toMatchObject({
      status: 'disconnected',
      error: ACTIVITY_SESSION_ENDED,
    });
  });

  it('ends the connection when the refresh resolves false', async () => {
    setActivityRefresher(null);
    const states = await connect99();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    expect(FakeSocket.instances).toHaveLength(1);
    expect(states.at(-1)).toMatchObject({
      status: 'disconnected',
      error: ACTIVITY_SESSION_ENDED,
    });
  });

  it('treats 4403 as terminal without refreshing or reconnecting', async () => {
    const refresher = vi.fn(async () => {});
    setActivityRefresher(refresher);
    const states = await connect99();
    FakeSocket.instances.at(-1)!.serverClose(4403);
    await flush();
    expect(refresher).not.toHaveBeenCalled();
    expect(FakeSocket.instances).toHaveLength(1);
    expect(states.at(-1)).toMatchObject({
      status: 'disconnected',
      error: ACTIVITY_OUT_OF_SCOPE,
    });
  });
});
