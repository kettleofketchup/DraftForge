import { describe, expect, it } from 'vitest';
import type { ChatMessage, ChatViewer, PendingChat } from '../../types';
import {
  CHAT_MESSAGE_CAP,
  addPending,
  applyChatAck,
  applyChatError,
  applyChatHistory,
  applyChatMessage,
  initialChatState,
  resetChatOnDisconnect,
  type ChatState,
} from '../chatState';

const member: ChatViewer = {
  role: 'member',
  team_id: 12,
  can_post_team: true,
  can_post_all: true,
};

function uuid(n: number): string {
  return `00000000-0000-4000-8000-${n.toString(16).padStart(12, '0')}`;
}

function ts(n: number): string {
  return `2026-11-20T18:00:00.${n.toString().padStart(6, '0')}Z`;
}

function msg(n: number, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: uuid(n),
    channel: 'team',
    team_id: 12,
    kind: 'text',
    hero_id: null,
    body: `m${n}`,
    created_at: ts(n),
    sender: {
      pk: 1,
      username: 'a',
      nickname: null,
      avatarUrl: null,
      discordId: null,
    },
    ...overrides,
  };
}

function pending(id: string, raw: string, sentAt = 1): PendingChat {
  return { clientMsgId: id, raw, sentAt };
}

const ids = (s: ChatState) => s.messages.map((m) => m.id);

describe('initialChatState', () => {
  it('starts empty and closed', () => {
    expect(initialChatState).toEqual({
      messages: [],
      viewer: null,
      pending: {},
      lastError: null,
      unread: 0,
      panelOpen: false,
      unavailable: false,
      resyncAfter: null,
    });
    expect(CHAT_MESSAGE_CAP).toBe(200);
  });
});

describe('applyChatHistory', () => {
  it('replaces messages and sets the viewer', () => {
    const before = applyChatMessage(initialChatState, msg(99));
    const after = applyChatHistory(before, member, [msg(1), msg(2)]);
    expect(ids(after)).toEqual([uuid(1), uuid(2)]);
    expect(after.viewer).toEqual(member);
  });

  it('keeps pending sends across a resync', () => {
    const s = addPending(initialChatState, pending('c1', 'hi'));
    expect(applyChatHistory(s, member, []).pending).toEqual({
      c1: pending('c1', 'hi'),
    });
  });
});

describe('applyChatMessage', () => {
  it('appends a new message', () => {
    const s = applyChatMessage(
      applyChatHistory(initialChatState, member, [msg(1)]),
      msg(2),
    );
    expect(ids(s)).toEqual([uuid(1), uuid(2)]);
  });

  it('ignores a duplicate id without counting it as unread', () => {
    const s1 = applyChatMessage(initialChatState, msg(1));
    const s2 = applyChatMessage(s1, msg(1, { body: 'changed' }));
    expect(s2).toBe(s1);
    expect(s2.unread).toBe(1);
  });

  it('inserts an out-of-order message in sorted position', () => {
    let s = applyChatHistory(initialChatState, member, [msg(1), msg(3)]);
    s = applyChatMessage(s, msg(2));
    expect(ids(s)).toEqual([uuid(1), uuid(2), uuid(3)]);
  });

  it('breaks created_at ties by id', () => {
    let s = applyChatMessage(initialChatState, msg(5, { created_at: ts(1) }));
    s = applyChatMessage(s, msg(4, { created_at: ts(1) }));
    expect(ids(s)).toEqual([uuid(4), uuid(5)]);
  });

  it(`caps the list at the newest ${200} messages`, () => {
    const history = Array.from({ length: CHAT_MESSAGE_CAP }, (_, i) =>
      msg(i + 1),
    );
    let s = applyChatHistory(initialChatState, member, history);
    s = applyChatMessage(s, msg(CHAT_MESSAGE_CAP + 1));
    expect(s.messages).toHaveLength(CHAT_MESSAGE_CAP);
    expect(s.messages[0].id).toBe(uuid(2));
    expect(s.messages.at(-1)?.id).toBe(uuid(CHAT_MESSAGE_CAP + 1));
  });

  it('drops a late message older than everything in a full list', () => {
    const history = Array.from({ length: CHAT_MESSAGE_CAP }, (_, i) =>
      msg(i + 2),
    );
    const s = applyChatMessage(
      applyChatHistory(initialChatState, member, history),
      msg(1),
    );
    expect(s.messages).toHaveLength(CHAT_MESSAGE_CAP);
    expect(ids(s)).not.toContain(uuid(1));
  });

  it('counts unread only while the panel is closed', () => {
    const closed = applyChatMessage(initialChatState, msg(1));
    expect(closed.unread).toBe(1);
    const open = applyChatMessage(
      { ...initialChatState, panelOpen: true },
      msg(1),
    );
    expect(open.unread).toBe(0);
  });
});

describe('pending, ack and error', () => {
  it('ack removes the pending send', () => {
    let s = addPending(initialChatState, pending('c1', 'hi'));
    s = addPending(s, pending('c2', 'yo'));
    s = applyChatAck(s, 'c1');
    expect(Object.keys(s.pending)).toEqual(['c2']);
    expect(s.lastError).toBeNull();
  });

  it('ack for an unknown id is a no-op', () => {
    const s = addPending(initialChatState, pending('c1', 'hi'));
    expect(applyChatAck(s, 'nope')).toBe(s);
  });

  it('error removes the pending send and keeps its text', () => {
    let s = addPending(initialChatState, pending('c1', 'ban invoker'));
    s = applyChatError(s, 'rate_limited', 'c1');
    expect(s.pending).toEqual({});
    expect(s.lastError).toEqual({ code: 'rate_limited', text: 'ban invoker' });
  });

  it('error without a matching pending send has no text', () => {
    const s = applyChatError(
      applyChatHistory(initialChatState, member, []),
      'unavailable',
    );
    expect(s.lastError).toEqual({ code: 'unavailable' });
    expect(s.unavailable).toBe(false);
  });

  it('marks chat unavailable when the bootstrap fails', () => {
    const s = applyChatError(initialChatState, 'unavailable');
    expect(s.unavailable).toBe(true);
    expect(s.lastError).toBeNull();
  });

  it('takes the viewer the server fell back to after a failure', () => {
    const spectator: ChatViewer = {
      role: 'spectator',
      team_id: null,
      can_post_team: false,
      can_post_all: false,
    };
    const live = applyChatHistory(initialChatState, member, [msg(1)]);
    const s = applyChatError(live, 'unavailable', undefined, spectator);
    expect(s.viewer).toEqual(spectator);
    expect(s.lastError).toEqual({ code: 'unavailable' });
    expect(ids(s)).toEqual([uuid(1)]);
    const boot = applyChatError(
      initialChatState,
      'unavailable',
      undefined,
      spectator,
    );
    expect(boot.viewer).toBeNull();
    expect(boot.unavailable).toBe(true);
  });

  it('a later history clears the unavailable mark', () => {
    const s = applyChatError(initialChatState, 'unavailable');
    expect(applyChatHistory(s, member, []).unavailable).toBe(false);
  });
});

describe('resetChatOnDisconnect', () => {
  it('surfaces a pending send as a not-sent error and clears the log', () => {
    let s = applyChatHistory(initialChatState, member, [msg(1)]);
    s = { ...s, panelOpen: true, unread: 3 };
    s = addPending(s, pending('c1', 'gl hf'));
    const after = resetChatOnDisconnect(s);
    expect(after.messages).toEqual([]);
    expect(after.viewer).toBeNull();
    expect(after.pending).toEqual({});
    expect(after.unread).toBe(3);
    expect(after.panelOpen).toBe(true);
    expect(after.lastError).toEqual({ code: 'unavailable', text: 'gl hf' });
  });

  it('reports the most recent pending text when several are in flight', () => {
    let s = addPending(initialChatState, pending('c1', 'first', 1));
    s = addPending(s, pending('c2', 'second', 2));
    expect(resetChatOnDisconnect(s).lastError).toEqual({
      code: 'unavailable',
      text: 'second',
    });
  });

  it('clears the error when nothing was in flight', () => {
    const s = applyChatError(initialChatState, 'rate_limited');
    expect(resetChatOnDisconnect(s).lastError).toBeNull();
  });
});

describe('unread across reconnects', () => {
  it("does not count the viewer's own live messages as unread", () => {
    let s = applyChatHistory(initialChatState, member, [], 1);
    s = applyChatMessage(s, msg(2), 1);
    expect(s.unread).toBe(0);
    s = applyChatMessage(s, msg(3, { sender: { ...msg(3).sender, pk: 2 } }), 1);
    expect(s.unread).toBe(1);
  });

  it("does not count the viewer's own messages from a resync", () => {
    let s = applyChatHistory(initialChatState, member, [msg(1)], 1);
    s = resetChatOnDisconnect(s);
    s = applyChatHistory(
      s,
      member,
      [msg(1), msg(2), msg(3, { sender: { ...msg(3).sender, pk: 2 } })],
      1,
    );
    expect(s.unread).toBe(1);
  });

  it('does not count the first history as unread', () => {
    const s = applyChatHistory(initialChatState, member, [msg(1), msg(2)]);
    expect(s.unread).toBe(0);
  });

  it('keeps unread and counts messages that arrived during the gap', () => {
    let s = applyChatHistory(initialChatState, member, [msg(1)]);
    s = applyChatMessage(s, msg(2));
    expect(s.unread).toBe(1);
    s = resetChatOnDisconnect(s);
    expect(s.unread).toBe(1);
    s = applyChatHistory(s, member, [msg(1), msg(2), msg(3), msg(4)]);
    expect(s.unread).toBe(3);
    expect(s.resyncAfter).toBeNull();
  });

  it('counts the whole history when the log was empty before the gap', () => {
    let s = applyChatHistory(initialChatState, member, []);
    s = resetChatOnDisconnect(s);
    s = applyChatHistory(s, member, [msg(1), msg(2)]);
    expect(s.unread).toBe(2);
  });

  it('keeps the first mark through a second disconnect', () => {
    let s = applyChatHistory(initialChatState, member, [msg(1)]);
    s = resetChatOnDisconnect(resetChatOnDisconnect(s));
    s = applyChatHistory(s, member, [msg(1), msg(2)]);
    expect(s.unread).toBe(1);
  });

  it('does not count a resync while the panel is open', () => {
    let s = applyChatHistory(initialChatState, member, [msg(1)]);
    s = resetChatOnDisconnect({ ...s, panelOpen: true });
    s = applyChatHistory(s, member, [msg(1), msg(2)]);
    expect(s.unread).toBe(0);
  });

  it('does not count history after a disconnect before any history', () => {
    let s = resetChatOnDisconnect(initialChatState);
    s = applyChatHistory(s, member, [msg(1), msg(2)]);
    expect(s.unread).toBe(0);
  });
});
