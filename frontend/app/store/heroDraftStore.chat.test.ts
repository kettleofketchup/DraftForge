// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = {
  connect: vi.fn((url: string) => `conn:${url}`),
  subscribe: vi.fn(() => () => {}),
  disconnect: vi.fn(),
  send: vi.fn((): boolean => true),
};

vi.mock('~/lib/websocket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/lib/websocket')>()),
  getWebSocketManager: () => manager,
}));

import {
  addPending,
  initialChatState,
} from '~/components/herodraft/chat/chatState';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const original = useHeroDraftStore.getState();

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => useHeroDraftStore.setState(original, true));

function connectedTo(draftId: number): void {
  useHeroDraftStore.getState().connect(draftId);
  useHeroDraftStore.setState({ status: 'connected' });
}

describe('heroDraftStore chat across drafts', () => {
  it('starts a fresh chat when a different draft is opened', () => {
    connectedTo(1);
    useHeroDraftStore.setState((s) => ({
      chat: addPending(
        { ...s.chat, panelOpen: true, unread: 4 },
        { clientMsgId: 'c1', raw: 'ban pudge', sentAt: 1 },
      ),
    }));
    useHeroDraftStore.getState().disconnect();
    expect(useHeroDraftStore.getState().chat.lastError?.text).toBe('ban pudge');

    useHeroDraftStore.getState().connect(2);
    expect(useHeroDraftStore.getState().chat).toEqual(initialChatState);
  });

  it('keeps the restored chat when the same draft reconnects', () => {
    connectedTo(1);
    useHeroDraftStore.setState((s) => ({
      chat: addPending(
        { ...s.chat, panelOpen: true },
        { clientMsgId: 'c1', raw: 'ban pudge', sentAt: 1 },
      ),
    }));
    useHeroDraftStore.getState().disconnect();
    useHeroDraftStore.getState().connect(1);
    const { chat } = useHeroDraftStore.getState();
    expect(chat.panelOpen).toBe(true);
    expect(chat.lastError).toEqual({ code: 'unavailable', text: 'ban pudge' });
  });

  it('switching drafts while connected also starts fresh', () => {
    connectedTo(1);
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, panelOpen: true, unread: 2 },
    }));
    useHeroDraftStore.getState().connect(2);
    expect(useHeroDraftStore.getState().chat).toEqual(initialChatState);
  });
});

describe('heroDraftStore chat error banner', () => {
  it('a later suggestion clears an earlier error', () => {
    connectedTo(1);
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, lastError: { code: 'rate_limited' } },
    }));
    expect(
      useHeroDraftStore.getState().suggestHero('suggest_pick', 5),
    ).not.toBeNull();
    expect(useHeroDraftStore.getState().chat.lastError).toBeNull();
  });

  it('keeps the error when the send is refused', () => {
    connectedTo(1);
    manager.send.mockReturnValueOnce(false);
    useHeroDraftStore.setState((s) => ({
      chat: { ...s.chat, lastError: { code: 'rate_limited' } },
    }));
    expect(useHeroDraftStore.getState().suggestHero('suggest_pick', 5)).toBe(
      null,
    );
    expect(useHeroDraftStore.getState().chat.lastError).toEqual({
      code: 'rate_limited',
    });
  });
});
