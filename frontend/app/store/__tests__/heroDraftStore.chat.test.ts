// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Handler = (msg: unknown) => void;
type StateChange = (s: {
  status: string;
  error: string | null;
  reconnectAttempts: number;
}) => void;

const handlers: Handler[] = [];
const stateChanges: StateChange[] = [];
const send = vi.fn((_id: string, _msg: unknown) => true);
const managerDisconnect = vi.fn();

vi.mock('~/lib/websocket', () => ({
  getWebSocketManager: () => ({
    connect: (_url: string, opts: { onStateChange: StateChange }) => {
      stateChanges.push(opts.onStateChange);
      return 'conn-1';
    },
    subscribe: (_id: string, h: Handler) => {
      handlers.push(h);
      return () => {};
    },
    send,
    disconnect: managerDisconnect,
  }),
}));

const { useHeroDraftStore } = await import('~/store/heroDraftStore');
const { addPending, initialChatState } =
  await import('~/components/herodraft/chat/chatState');

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const sender = {
  pk: 5,
  username: 'mem_a',
  nickname: null,
  avatarUrl: null,
  discordId: null,
};
const msg = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  channel: 'team',
  team_id: 12,
  kind: 'text',
  hero_id: null,
  body: `m${n}`,
  created_at: `2026-11-20T18:00:0${n}.000000Z`,
  sender,
  ...extra,
});
const memberViewer = {
  role: 'member',
  team_id: 12,
  can_post_team: true,
  can_post_all: true,
};

const emit = (m: unknown) => handlers[handlers.length - 1](m);
const setStatus = (status: string) =>
  stateChanges[stateChanges.length - 1]({
    status,
    error: null,
    reconnectAttempts: 0,
  });
const chat = () => useHeroDraftStore.getState().chat;
const sentPayloads = () => send.mock.calls.map((c) => c[1]);

beforeEach(() => {
  handlers.length = 0;
  stateChanges.length = 0;
  send.mockClear();
  send.mockImplementation(() => true);
  useHeroDraftStore.getState().reset();
  useHeroDraftStore.getState().connect(2);
  setStatus('connected');
});
afterEach(() => useHeroDraftStore.getState().disconnect());

describe('heroDraftStore chat frames', () => {
  it('chat_history sets viewer and messages', () => {
    emit({
      type: 'chat_history',
      viewer: memberViewer,
      messages: [msg(2), msg(1)],
    });
    expect(chat().viewer).toEqual(memberViewer);
    expect(chat().messages.map((m) => m.body)).toEqual(['m1', 'm2']);
  });

  it('chat_message inserts and de-duplicates', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    emit({ type: 'chat_message', message: msg(3) });
    emit({ type: 'chat_message', message: msg(2) });
    emit({ type: 'chat_message', message: msg(3) });
    expect(chat().messages.map((m) => m.body)).toEqual(['m1', 'm2', 'm3']);
    expect(chat().unread).toBe(2);
  });

  it('chat_ack clears the matching pending send', () => {
    const id = useHeroDraftStore.getState().sendChat('hi');
    expect(id).not.toBeNull();
    expect(Object.keys(chat().pending)).toEqual([id]);
    emit({ type: 'chat_ack', client_msg_id: id, id: msg(1).id });
    expect(chat().pending).toEqual({});
  });

  it('chat_ack without client_msg_id leaves pending alone', () => {
    const id = useHeroDraftStore.getState().sendChat('hi');
    emit({ type: 'chat_ack', id: msg(1).id });
    expect(Object.keys(chat().pending)).toEqual([id]);
  });

  it('chat_error clears pending and records the failed text', () => {
    const id = useHeroDraftStore.getState().sendChat('too spicy');
    emit({ type: 'chat_error', code: 'rate_limited', client_msg_id: id });
    expect(chat().pending).toEqual({});
    expect(chat().lastError).toEqual({
      code: 'rate_limited',
      text: 'too spicy',
    });
  });

  it('chat_error unavailable before any viewer marks chat unavailable', () => {
    emit({ type: 'chat_error', code: 'unavailable' });
    expect(chat().unavailable).toBe(true);
    expect(chat().lastError).toBeNull();
  });

  it('chat_error without client_msg_id sets the code only once a viewer is known', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [] });
    emit({ type: 'chat_error', code: 'unavailable' });
    expect(chat().lastError).toEqual({ code: 'unavailable' });
    expect(chat().unavailable).toBe(false);
  });

  it('chat_error with a viewer downgrades the composer to that viewer', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [] });
    emit({
      type: 'chat_error',
      code: 'unavailable',
      viewer: {
        role: 'spectator',
        team_id: null,
        can_post_team: false,
        can_post_all: false,
      },
    });
    expect(chat().viewer?.role).toBe('spectator');
    expect(chat().lastError).toEqual({ code: 'unavailable' });
  });
});

describe('heroDraftStore chat actions', () => {
  it('sendChat sends the raw body with a uuid client_msg_id and nothing else', () => {
    const id = useHeroDraftStore.getState().sendChat('/all hi');
    expect(id).toMatch(UUID_V4);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0]).toBe('conn-1');
    const payload = sentPayloads()[0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      'body',
      'client_msg_id',
      'type',
    ]);
    expect(payload).toEqual({
      type: 'chat_send',
      body: '/all hi',
      client_msg_id: id,
    });
    expect(payload).not.toHaveProperty('channel');
    expect(payload).not.toHaveProperty('team_id');
    expect(chat().pending[id as string]).toMatchObject({
      clientMsgId: id,
      raw: '/all hi',
    });
  });

  it.each(['', '   ', '/all', '/all  ', '\n\t'])(
    'sendChat(%j) sends nothing and returns null',
    (raw) => {
      expect(useHeroDraftStore.getState().sendChat(raw)).toBeNull();
      expect(send).not.toHaveBeenCalled();
      expect(chat().pending).toEqual({});
    },
  );

  it('sendChat returns null while not connected', () => {
    setStatus('reconnecting');
    expect(useHeroDraftStore.getState().sendChat('hi')).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it('sendChat returns null when the manager refuses the send', () => {
    send.mockImplementation(() => false);
    expect(useHeroDraftStore.getState().sendChat('hi')).toBeNull();
    expect(chat().pending).toEqual({});
  });

  it('suggestHero sends exactly type, kind, hero_id and client_msg_id', () => {
    const id = useHeroDraftStore.getState().suggestHero('suggest_ban', 74);
    expect(id).toMatch(UUID_V4);
    expect(sentPayloads()[0]).toEqual({
      type: 'chat_suggest',
      kind: 'suggest_ban',
      hero_id: 74,
      client_msg_id: id,
    });
    expect(
      Object.keys(sentPayloads()[0] as Record<string, unknown>).sort(),
    ).toEqual(['client_msg_id', 'hero_id', 'kind', 'type']);
  });

  it('suggestHero returns null while not connected', () => {
    setStatus('disconnected');
    expect(
      useHeroDraftStore.getState().suggestHero('suggest_pick', 1),
    ).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it('setChatPanelOpen opens the panel and clears unread', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [] });
    emit({ type: 'chat_message', message: msg(1) });
    expect(chat().unread).toBe(1);
    useHeroDraftStore.getState().setChatPanelOpen(true);
    expect(chat().panelOpen).toBe(true);
    expect(chat().unread).toBe(0);
    emit({ type: 'chat_message', message: msg(2) });
    expect(chat().unread).toBe(0);
    useHeroDraftStore.getState().setChatPanelOpen(false);
    expect(chat().panelOpen).toBe(false);
  });

  it('clearChatError clears lastError', () => {
    emit({ type: 'chat_error', code: 'empty' });
    useHeroDraftStore.getState().clearChatError();
    expect(chat().lastError).toBeNull();
  });
});

describe('heroDraftStore chat disconnect', () => {
  it('surfaces pending sends as not-sent on disconnect', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    useHeroDraftStore.getState().sendChat('gl hf');
    setStatus('reconnecting');
    expect(chat().pending).toEqual({});
    expect(chat().lastError).toEqual({ code: 'unavailable', text: 'gl hf' });
    expect(chat().messages).toEqual([]);
    expect(chat().viewer).toBeNull();
  });

  it('a fresh chat_history after reconnect replaces the log', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    setStatus('reconnecting');
    setStatus('connected');
    emit({
      type: 'chat_history',
      viewer: { ...memberViewer, role: 'spectator', team_id: null },
      messages: [msg(2, { channel: 'all', team_id: null })],
    });
    expect(chat().messages.map((m) => m.body)).toEqual(['m2']);
    expect(chat().viewer?.role).toBe('spectator');
  });

  it('disconnect() resets chat but reports the pending send', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    useHeroDraftStore.getState().setChatPanelOpen(true);
    useHeroDraftStore.getState().sendChat('wait');
    useHeroDraftStore.getState().disconnect();
    expect(chat().messages).toEqual([]);
    expect(chat().viewer).toBeNull();
    expect(chat().pending).toEqual({});
    expect(chat().lastError).toEqual({ code: 'unavailable', text: 'wait' });
  });

  it('disconnect() with nothing pending leaves no error', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    useHeroDraftStore.getState().disconnect();
    expect(chat().messages).toEqual([]);
    expect(chat().lastError).toBeNull();
  });

  it('reset() clears chat completely', () => {
    useHeroDraftStore.getState().sendChat('wait');
    useHeroDraftStore.getState().reset();
    expect(chat().lastError).toBeNull();
    expect(chat().pending).toEqual({});
  });

  it('staying connected does not clear chat', () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    setStatus('connected');
    expect(chat().messages).toHaveLength(1);
  });
});

describe('heroDraftStore chat across drafts', () => {
  it('starts a fresh chat when a different draft is opened', () => {
    useHeroDraftStore.setState((s) => ({
      chat: addPending(
        { ...s.chat, panelOpen: true, unread: 4 },
        { clientMsgId: 'c1', raw: 'ban pudge', sentAt: 1 },
      ),
    }));
    useHeroDraftStore.getState().disconnect();
    expect(chat().lastError?.text).toBe('ban pudge');

    useHeroDraftStore.getState().connect(3);
    expect(chat()).toEqual(initialChatState);
  });

  it('keeps the restored chat when the same draft reconnects', () => {
    useHeroDraftStore.setState((s) => ({
      chat: addPending(
        { ...s.chat, panelOpen: true },
        { clientMsgId: 'c1', raw: 'ban pudge', sentAt: 1 },
      ),
    }));
    useHeroDraftStore.getState().disconnect();
    useHeroDraftStore.getState().connect(2);
    expect(chat().panelOpen).toBe(true);
    expect(chat().lastError).toEqual({
      code: 'unavailable',
      text: 'ban pudge',
    });
  });

  it('switching drafts while connected also starts fresh', () => {
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, panelOpen: true, unread: 2 },
    }));
    useHeroDraftStore.getState().connect(3);
    expect(chat()).toEqual(initialChatState);
  });
});

describe('heroDraftStore chat error banner', () => {
  it('a later suggestion clears an earlier error', () => {
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, lastError: { code: 'rate_limited' } },
    }));
    expect(
      useHeroDraftStore.getState().suggestHero('suggest_pick', 5),
    ).not.toBeNull();
    expect(chat().lastError).toBeNull();
  });

  it('keeps the error when the send is refused', () => {
    send.mockImplementation(() => false);
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, lastError: { code: 'rate_limited' } },
    }));
    expect(
      useHeroDraftStore.getState().suggestHero('suggest_pick', 5),
    ).toBeNull();
    expect(chat().lastError).toEqual({ code: 'rate_limited' });
  });
});

describe('heroDraftStore chat on close and identity change', () => {
  const seedChatState = () => {
    emit({ type: 'chat_history', viewer: memberViewer, messages: [msg(1)] });
    emit({ type: 'chat_message', message: msg(2) });
    emit({ type: 'chat_error', code: 'rate_limited' });
    useHeroDraftStore.getState().sendChat('unsent');
  };

  it('a same-user disconnect() and reconnect to the same draft keeps unread', () => {
    seedChatState();
    useHeroDraftStore.getState().disconnect();
    useHeroDraftStore.getState().connect(2);
    expect(chat().unread).toBe(1);
    expect(chat().resyncAfter).toEqual({ after: expect.anything() });
    expect(chat().lastError).toEqual({ code: 'unavailable', text: 'unsent' });
  });

  it('reset() then connect() to the same draft starts from the initial chat', () => {
    seedChatState();
    useHeroDraftStore.getState().setChatPanelOpen(true);
    useHeroDraftStore.getState().setChatPanelOpen(false);
    emit({ type: 'chat_message', message: msg(3) });
    useHeroDraftStore.getState().reset();
    expect(chat()).toEqual(initialChatState);
    useHeroDraftStore.getState().connect(2);
    expect(chat()).toEqual(initialChatState);
  });
});
