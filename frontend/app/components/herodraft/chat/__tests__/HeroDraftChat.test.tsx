// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

let isDesktop = true;
vi.mock('~/hooks/useMediaQuery', () => ({
  useMediaQuery: () => isDesktop,
}));

import { HeroDraftChat } from '~/components/herodraft/chat/HeroDraftChat';
import { initialChatState } from '~/components/herodraft/chat/chatState';
import type { ChatMessage, ChatViewer } from '~/components/herodraft/types';
import { getHeroName } from '~/lib/dota/heroes';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const sender = {
  pk: 5,
  username: 'mem_a',
  nickname: null,
  avatarUrl: null,
  discordId: null,
};
const msg = (n: number, extra: Partial<ChatMessage> = {}): ChatMessage => ({
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
const member: ChatViewer = {
  role: 'member',
  team_id: 12,
  can_post_team: true,
  can_post_all: true,
};
const spectator: ChatViewer = {
  role: 'spectator',
  team_id: null,
  can_post_team: false,
  can_post_all: false,
};

const sendChat = vi.fn((_raw: string): string | null => 'c1');
const original = useHeroDraftStore.getState();

function seed(viewer: ChatViewer | null, messages: ChatMessage[] = []) {
  useHeroDraftStore.setState({
    status: 'connected',
    chat: { ...initialChatState, viewer, messages },
    sendChat,
    selectedHeroId: null,
  });
}

const input = () => screen.getByTestId('herodraft-chat-input');
const send = () => screen.getByTestId('herodraft-chat-send');

beforeEach(() => {
  isDesktop = true;
  sendChat.mockClear();
  sendChat.mockImplementation(() => 'c1');
});
afterEach(() => useHeroDraftStore.setState(original, true));

describe('HeroDraftChat composer', () => {
  it('member composer targets team and switches to all for /all', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    expect(input()).toBeEnabled();
    expect(screen.getByTestId('herodraft-chat-target')).toHaveTextContent(
      'TEAM',
    );
    fireEvent.change(input(), { target: { value: '/all hi' } });
    expect(screen.getByTestId('herodraft-chat-target')).toHaveTextContent(
      'ALL',
    );
    fireEvent.submit(input().closest('form')!);
    expect(sendChat).toHaveBeenCalledWith('/all hi');
    expect(input()).toHaveValue('');
  });

  it('disables send for /all alone', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    fireEvent.change(input(), { target: { value: '/all' } });
    expect(send()).toBeDisabled();
    fireEvent.submit(input().closest('form')!);
    expect(sendChat).not.toHaveBeenCalled();
  });

  it('keeps the text when the store refuses the send', () => {
    seed(member);
    sendChat.mockImplementation(() => null);
    render(<HeroDraftChat draftState="drafting" />);
    fireEvent.change(input(), { target: { value: 'hello' } });
    fireEvent.submit(input().closest('form')!);
    expect(input()).toHaveValue('hello');
  });

  it('spectator composer is read-only with no construction notice', () => {
    seed(spectator);
    render(<HeroDraftChat draftState="drafting" />);
    expect(input()).toBeDisabled();
    expect(send()).toBeDisabled();
    expect(input()).toHaveAttribute(
      'placeholder',
      'Spectators can read all chat',
    );
    expect(document.body.textContent).not.toMatch(/under construction/i);
  });

  it('restores failed text when the input is still empty', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    fireEvent.change(input(), { target: { value: 'hello' } });
    fireEvent.submit(input().closest('form')!);
    expect(input()).toHaveValue('');
    act(() =>
      useHeroDraftStore.setState({
        chat: {
          ...useHeroDraftStore.getState().chat,
          lastError: { code: 'rate_limited', text: 'hello' },
        },
      }),
    );
    expect(input()).toHaveValue('hello');
    const error = screen.getByTestId('herodraft-chat-error');
    expect(error).toHaveTextContent('Slow down a moment');
    expect(error).not.toHaveTextContent('hello');
  });

  it('shows failed text in the error line when the user typed again', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    fireEvent.change(input(), { target: { value: 'hello' } });
    fireEvent.submit(input().closest('form')!);
    fireEvent.change(input(), { target: { value: 'next' } });
    act(() =>
      useHeroDraftStore.setState({
        chat: {
          ...useHeroDraftStore.getState().chat,
          lastError: { code: 'rate_limited', text: 'hello' },
        },
      }),
    );
    expect(input()).toHaveValue('next');
    expect(screen.getByTestId('herodraft-chat-error')).toHaveTextContent(
      'hello',
    );
  });

  it('dismisses the error line', () => {
    seed(member);
    useHeroDraftStore.setState({
      chat: {
        ...useHeroDraftStore.getState().chat,
        lastError: { code: 'hero_unavailable' },
      },
    });
    render(<HeroDraftChat draftState="drafting" />);
    fireEvent.click(screen.getByTestId('herodraft-chat-error-dismiss'));
    expect(screen.queryByTestId('herodraft-chat-error')).toBeNull();
    expect(useHeroDraftStore.getState().chat.lastError).toBeNull();
  });

  it('shows chat unavailable when the server could not start chat', () => {
    seed(null);
    useHeroDraftStore.setState({
      chat: { ...useHeroDraftStore.getState().chat, unavailable: true },
    });
    render(<HeroDraftChat draftState="drafting" />);
    expect(input()).toBeDisabled();
    expect(input()).toHaveAttribute('placeholder', 'Chat unavailable');
    expect(send()).toBeDisabled();
    expect(screen.queryByTestId('herodraft-chat-error')).toBeNull();
  });
});

describe('HeroDraftChat log', () => {
  const openPanel = () =>
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));

  it('renders a hostile body as literal text (T13)', () => {
    const body = '<img src=x onerror=alert(1)>';
    seed(member, [msg(1, { body })]);
    render(<HeroDraftChat draftState="drafting" />);
    openPanel();
    expect(screen.getByTestId('herodraft-chat-log')).toHaveTextContent(body);
    expect(document.querySelector('img[src="x"]')).toBeNull();
  });

  it('rows carry channel, kind and hero data attributes', () => {
    const m = msg(2, { kind: 'suggest_ban', hero_id: 74, body: '' });
    seed(member, [msg(1, { channel: 'all', team_id: null }), m]);
    render(<HeroDraftChat draftState="drafting" />);
    openPanel();
    const row = screen.getByTestId(`herodraft-chat-message-${m.id}`);
    expect(row).toHaveAttribute('data-channel', 'team');
    expect(row).toHaveAttribute('data-kind', 'suggest_ban');
    expect(row).toHaveAttribute('data-hero-id', '74');
    const allRow = screen.getByTestId(`herodraft-chat-message-${msg(1).id}`);
    expect(allRow).toHaveAttribute('data-channel', 'all');
    expect(allRow).toHaveTextContent('ALL');
    expect(row).toHaveTextContent('TEAM');
  });

  it('suggestion row shows the hero and selects it on click', () => {
    const m = msg(3, { kind: 'suggest_pick', hero_id: 74, body: '' });
    seed(member, [m]);
    render(<HeroDraftChat draftState="drafting" />);
    openPanel();
    const suggestion = screen.getByTestId(`herodraft-chat-suggestion-${m.id}`);
    expect(suggestion).toHaveTextContent(getHeroName(74));
    expect(suggestion).toHaveTextContent('PICK');
    fireEvent.click(suggestion);
    expect(useHeroDraftStore.getState().selectedHeroId).toBe(74);
  });

  it('shows the unread count on the toggle', () => {
    seed(member);
    useHeroDraftStore.setState({
      chat: { ...useHeroDraftStore.getState().chat, unread: 3 },
    });
    render(<HeroDraftChat draftState="drafting" />);
    expect(screen.getByTestId('herodraft-chat-unread')).toHaveTextContent('3');
  });

  it('opens the panel when the input is focused', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    expect(screen.queryByTestId('herodraft-chat-panel')).toBeNull();
    fireEvent.focus(input());
    expect(screen.getByTestId('herodraft-chat-panel')).toBeInTheDocument();
    fireEvent.keyDown(input(), { key: 'Escape' });
    expect(screen.queryByTestId('herodraft-chat-panel')).toBeNull();
  });
});

describe('HeroDraftChat below md', () => {
  it('renders only the toggle until opened, then one composer in a sheet', () => {
    isDesktop = false;
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    expect(screen.getByTestId('herodraft-chat-toggle')).toBeInTheDocument();
    expect(screen.queryAllByTestId('herodraft-chat-input')).toHaveLength(0);
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    const sheet = screen.getByTestId('herodraft-chat-sheet');
    expect(sheet).toHaveAttribute('data-herodraft-chat');
    expect(screen.getAllByTestId('herodraft-chat-input')).toHaveLength(1);
    expect(document.activeElement).toBe(input());
  });
});
