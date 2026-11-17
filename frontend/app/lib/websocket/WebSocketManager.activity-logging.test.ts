// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  setActivityCredential,
  setActivityRefresher,
  type ActivityCredential,
} from '~/lib/activity-session';
import { getWebSocketManager } from './WebSocketManager';

const { mockLog } = vi.hoisted(() => ({
  mockLog: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));
vi.mock('~/lib/logger', () => ({ getLogger: () => mockLog }));

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

const credential = (token: string): ActivityCredential => ({
  token,
  scope: 'tournament',
  tournament_id: 5,
  pin: null,
  site_url: 'https://site.test',
});

const flush = async () => {
  await vi.runAllTimersAsync();
};

const connect = async () => {
  getWebSocketManager().connect(
    `wss://${window.location.host}/api/herodraft/99/`,
  );
  await flush();
};

const endedWith = (reason: string) =>
  expect(mockLog.warn).toHaveBeenCalledWith(
    'activity_session_ended',
    expect.objectContaining({ reason }),
  );

beforeEach(() => {
  vi.useFakeTimers();
  FakeSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeSocket);
  setActivityCredential(credential('old-token'));
  Object.values(mockLog).forEach((fn) => fn.mockClear());
});
afterEach(() => {
  getWebSocketManager().disconnectAll();
  setActivityRefresher(null);
  setActivityCredential(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('Activity terminal socket logging', () => {
  it('warns when the refreshed credential is rejected again', async () => {
    setActivityRefresher(async () => {
      setActivityCredential(credential('new-token'));
    });
    await connect();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    vi.advanceTimersByTime(60_000);
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    endedWith('refreshed_credential_rejected');
  });

  it('warns when the credential refresh fails', async () => {
    setActivityRefresher(null);
    await connect();
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    endedWith('refresh_failed');
  });

  it('warns when a 4401 arrives with no credential', async () => {
    await connect();
    setActivityCredential(null);
    FakeSocket.instances.at(-1)!.serverClose(4401);
    await flush();
    endedWith('no_credential');
  });

  it('warns when a reconnect finds no credential', async () => {
    await connect();
    setActivityCredential(null);
    FakeSocket.instances.at(-1)!.serverClose(1006);
    await flush();
    expect(FakeSocket.instances).toHaveLength(1);
    endedWith('no_credential');
  });

  it('warns, not info, when the socket is out of scope', async () => {
    await connect();
    FakeSocket.instances.at(-1)!.serverClose(4403);
    await flush();
    expect(mockLog.warn).toHaveBeenCalledWith(
      'activity_socket_out_of_scope',
      expect.anything(),
    );
  });
});
