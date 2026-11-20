// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const observers: ResizeObserverCallback[] = [];
class CapturingResizeObserver {
  constructor(cb: ResizeObserverCallback) {
    observers.push(cb);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  CapturingResizeObserver as unknown as typeof ResizeObserver;

let isDesktop = true;
vi.mock('~/hooks/useMediaQuery', () => ({
  useMediaQuery: () => isDesktop,
}));

import { HeroDraftChat } from '~/components/herodraft/chat/HeroDraftChat';
import {
  PREVIEW_FADE_MS,
  PREVIEW_TTL_MS,
} from '~/components/herodraft/chat/chatPreview';
import {
  applyChatHistory,
  applyChatMessage,
  initialChatState,
} from '~/components/herodraft/chat/chatState';
import type { ChatMessage, ChatViewer } from '~/components/herodraft/types';
import { getHeroName } from '~/lib/dota/heroes';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';

const SELF = 5;
const TEAMMATE = 6;
const OPPONENT = 9;

const user = (pk: number) => ({
  pk,
  username: `user${pk}`,
  nickname: null,
  avatar: null,
});
let seq = 0;
const msg = (
  senderPk: number,
  extra: Partial<ChatMessage> = {},
): ChatMessage => {
  seq += 1;
  return {
    id: `00000000-0000-4000-8000-${String(seq).padStart(12, '0')}`,
    channel: 'team',
    team_id: 12,
    kind: 'text',
    hero_id: null,
    body: `m${seq}`,
    created_at: `2026-11-20T18:00:00.${String(seq).padStart(6, '0')}Z`,
    sender: user(senderPk),
    ...extra,
  };
};
const allChat = (senderPk: number, body?: string) =>
  msg(senderPk, { channel: 'all', team_id: null, ...(body ? { body } : {}) });

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
const team = (tournament_team: number, captain: number, members: number[]) => ({
  tournament_team,
  captain: user(captain),
  members: members.map(user),
});

const originalDraft = useHeroDraftStore.getState();
const originalUser = useUserStore.getState();

function seed(viewer: ChatViewer, history: ChatMessage[] = []) {
  useHeroDraftStore.setState({
    status: 'connected',
    draft: {
      draft_teams: [team(12, SELF, [TEAMMATE]), team(13, 8, [OPPONENT])],
    } as never,
    chat: applyChatHistory(initialChatState, viewer, history, SELF),
    chatPanelInset: 0,
  });
}

function deliver(m: ChatMessage) {
  act(() =>
    useHeroDraftStore.setState({
      chat: applyChatMessage(useHeroDraftStore.getState().chat, m, SELF),
    }),
  );
}

const strip = () => screen.queryByTestId('herodraft-chat-preview');
const lines = () => screen.queryAllByTestId('herodraft-chat-preview-line');

beforeEach(() => {
  isDesktop = true;
  observers.length = 0;
  vi.useFakeTimers();
  useUserStore.setState({ currentUser: { pk: SELF } as never });
});
afterEach(() => {
  vi.useRealTimers();
  useHeroDraftStore.setState(originalDraft, true);
  useUserStore.setState(originalUser, true);
});

describe('HeroDraftChat closed-state preview', () => {
  it('shows a teammate message in a click-through strip', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    expect(strip()).toBeNull();
    deliver(msg(TEAMMATE, { body: 'take axe' }));
    expect(strip()).toHaveClass('pointer-events-none');
    expect(lines()).toHaveLength(1);
    expect(lines()[0]).toHaveTextContent('user6');
    expect(lines()[0]).toHaveTextContent('take axe');
    expect(lines()[0]).toHaveClass('truncate');
  });

  it('previews all chat from teammates but not from the other team', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(allChat(OPPONENT, 'ez'));
    expect(strip()).toBeNull();
    expect(useHeroDraftStore.getState().chat.unread).toBe(1);
    deliver(allChat(TEAMMATE, 'glhf'));
    expect(lines()).toHaveLength(1);
    expect(lines()[0]).toHaveTextContent('glhf');
    expect(lines()[0]).toHaveTextContent('ALL');
  });

  it('collapses repeats from one sender into a counted line', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(msg(TEAMMATE, { body: 'a' }));
    deliver(msg(TEAMMATE, { body: 'b' }));
    deliver(msg(TEAMMATE, { body: 'c' }));
    expect(lines()).toHaveLength(1);
    expect(lines()[0]).toHaveTextContent('c');
    expect(lines()[0]).not.toHaveTextContent(': a');
    expect(
      screen.getByTestId('herodraft-chat-preview-count'),
    ).toHaveTextContent('×3');
  });

  it('keeps at most two lines, newest replacing oldest', () => {
    seed(spectator);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(allChat(TEAMMATE, 'one'));
    deliver(allChat(OPPONENT, 'two'));
    deliver(allChat(8, 'three'));
    expect(lines().map((l) => l.textContent)).toEqual([
      expect.stringContaining('two'),
      expect.stringContaining('three'),
    ]);
  });

  it('fades each line out and removes it after the TTL', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(msg(TEAMMATE));
    expect(lines()[0]).not.toHaveClass('opacity-0');
    expect(lines()[0]).toHaveClass('motion-reduce:transition-none');
    act(() => vi.advanceTimersByTime(PREVIEW_TTL_MS - PREVIEW_FADE_MS));
    expect(lines()[0]).toHaveClass('opacity-0');
    act(() => vi.advanceTimersByTime(PREVIEW_FADE_MS));
    expect(strip()).toBeNull();
  });

  it('shows nothing while the panel is open and clears on open', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(msg(TEAMMATE));
    expect(lines()).toHaveLength(1);
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    expect(strip()).toBeNull();
    deliver(msg(TEAMMATE));
    expect(strip()).toBeNull();
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    expect(strip()).toBeNull();
  });

  it('never previews history or a resync', () => {
    seed(member, [msg(TEAMMATE)]);
    render(<HeroDraftChat draftState="drafting" />);
    expect(strip()).toBeNull();
    act(() =>
      useHeroDraftStore.setState({
        chat: applyChatHistory(
          useHeroDraftStore.getState().chat,
          member,
          [msg(TEAMMATE), msg(TEAMMATE)],
          SELF,
        ),
      }),
    );
    expect(strip()).toBeNull();
  });

  it('spectators preview all chat from both teams', () => {
    seed(spectator);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(allChat(OPPONENT, 'from b'));
    expect(lines()).toHaveLength(1);
    expect(lines()[0]).toHaveTextContent('from b');
  });

  it('previews your own suggestions but not your own text', () => {
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(msg(SELF, { body: 'mine' }));
    expect(strip()).toBeNull();
    deliver(msg(SELF, { kind: 'suggest_pick', hero_id: 74, body: '' }));
    expect(lines()[0]).toHaveTextContent(getHeroName(74));
    expect(lines()[0]).toHaveTextContent('PICK');
  });

  it('has no preview below md', () => {
    isDesktop = false;
    seed(member);
    render(<HeroDraftChat draftState="drafting" />);
    deliver(msg(TEAMMATE));
    expect(strip()).toBeNull();
  });
});

describe('HeroDraftChat panel inset', () => {
  it('reports the open panel height for the hero grid and zero when closed', () => {
    seed(member);
    const rect = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function (this: HTMLElement) {
        const top =
          this.dataset.testid === 'herodraft-chat-overlay' ? 500 : 820;
        return { top } as DOMRect;
      });
    render(<HeroDraftChat draftState="drafting" />);
    expect(useHeroDraftStore.getState().chatPanelInset).toBe(0);
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    expect(useHeroDraftStore.getState().chatPanelInset).toBe(320);
    rect.mockImplementation(function (this: HTMLElement) {
      const top = this.dataset.testid === 'herodraft-chat-overlay' ? 400 : 820;
      return { top } as DOMRect;
    });
    act(() => observers.forEach((cb) => cb([], {} as ResizeObserver)));
    expect(useHeroDraftStore.getState().chatPanelInset).toBe(420);
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    expect(useHeroDraftStore.getState().chatPanelInset).toBe(0);
    rect.mockRestore();
  });
});
