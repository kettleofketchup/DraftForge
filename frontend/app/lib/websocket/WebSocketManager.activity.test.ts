// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  setActivityCredential,
  setActivityRefresher,
} from '~/lib/activity-session';
import { getWebSocketManager } from './WebSocketManager';

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

const flush = async () => {
  await vi.runAllTimersAsync();
};

beforeEach(() => {
  vi.useFakeTimers();
  FakeSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeSocket);
  setActivityCredential({ kind: 'hero', draft_id: 7, token: 'old-token' });
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
      setActivityCredential({ kind: 'hero', draft_id: 7, token: 'new-token' });
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
