// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('~/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }));

import { HeroGrid } from '~/components/herodraft/HeroGrid';
import { HeroDraftChat } from '~/components/herodraft/chat/HeroDraftChat';
import { initialChatState } from '~/components/herodraft/chat/chatState';
import type { HeroDraft } from '~/components/herodraft/types';
import { getHeroName } from '~/lib/dota/heroes';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';

const PICKED_HERO = 1;
const FREE_HERO = 2;

const suggestHero = vi.fn(
  (_kind: string, _heroId: number): string | null => 'c1',
);
const original = useHeroDraftStore.getState();
const originalUser = useUserStore.getState();

beforeEach(() => {
  suggestHero.mockClear();
  useHeroDraftStore.setState({
    status: 'connected',
    draft: {
      rounds: [{ hero_id: PICKED_HERO }],
    } as unknown as HeroDraft,
    chat: { ...initialChatState },
    suggestHero,
    searchQuery: '',
    selectedHeroId: null,
  });
});
afterEach(() => useHeroDraftStore.setState(original, true));

function renderGrid(canSuggest: boolean, isMyTurn = true) {
  return render(
    <HeroGrid
      onHeroClick={() => {}}
      disabled={!isMyTurn}
      showActionButton
      currentAction="pick"
      isMyTurn={isMyTurn}
      canSuggest={canSuggest}
    />,
  );
}

const hero = (id: number) => screen.getByTestId(`herodraft-hero-${id}`);

describe('HeroGrid suggestion context menu', () => {
  it('renders no menu and keeps the native menu when canSuggest is false', () => {
    renderGrid(false);
    const notPrevented = fireEvent.contextMenu(hero(FREE_HERO));
    expect(notPrevented).toBe(true);
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByTestId('herodraft-hero-suggest-pick')).toBeNull();
  });

  it('opens a menu for the right-clicked hero', () => {
    renderGrid(true);
    fireEvent.contextMenu(hero(FREE_HERO));
    const menu = screen.getByRole('menu');
    expect(within(menu).getByText(getHeroName(FREE_HERO))).toBeTruthy();
    expect(
      within(menu).getByTestId('herodraft-hero-suggest-pick'),
    ).toBeTruthy();
    expect(within(menu).getByTestId('herodraft-hero-suggest-ban')).toBeTruthy();
  });

  it('suggests a ban without opening the chat panel', () => {
    renderGrid(true);
    fireEvent.contextMenu(hero(FREE_HERO));
    fireEvent.click(screen.getByTestId('herodraft-hero-suggest-ban'));
    expect(suggestHero).toHaveBeenCalledWith('suggest_ban', FREE_HERO);
    expect(useHeroDraftStore.getState().chat.panelOpen).toBe(false);
  });

  it('keeps an open chat panel open through right-click and suggest', () => {
    render(
      <>
        <HeroGrid
          onHeroClick={() => {}}
          disabled={false}
          showActionButton
          currentAction="pick"
          isMyTurn
          canSuggest
        />
        <HeroDraftChat draftState="drafting" />
      </>,
    );
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    const panelOpen = () => useHeroDraftStore.getState().chat.panelOpen;
    expect(panelOpen()).toBe(true);

    fireEvent.pointerDown(hero(FREE_HERO), { button: 2 });
    fireEvent.contextMenu(hero(FREE_HERO));
    expect(panelOpen()).toBe(true);

    const item = screen.getByTestId('herodraft-hero-suggest-pick');
    fireEvent.pointerDown(item, { button: 0 });
    fireEvent.click(item);
    expect(suggestHero).toHaveBeenCalledWith('suggest_pick', FREE_HERO);
    expect(panelOpen()).toBe(true);
    expect(screen.getByTestId('herodraft-chat-panel')).toBeInTheDocument();
  });

  it('still closes the chat panel on a left click outside it', () => {
    render(
      <>
        <HeroGrid
          onHeroClick={() => {}}
          disabled={false}
          showActionButton
          currentAction="pick"
          isMyTurn
          canSuggest
        />
        <HeroDraftChat draftState="drafting" />
      </>,
    );
    fireEvent.click(screen.getByTestId('herodraft-chat-toggle'));
    fireEvent.pointerDown(hero(FREE_HERO), { button: 0 });
    expect(useHeroDraftStore.getState().chat.panelOpen).toBe(false);
  });

  it('suggests a pick', () => {
    renderGrid(true);
    fireEvent.contextMenu(hero(FREE_HERO));
    fireEvent.click(screen.getByTestId('herodraft-hero-suggest-pick'));
    expect(suggestHero).toHaveBeenCalledWith('suggest_pick', FREE_HERO);
  });

  it('opens nothing for a right-click on the grid background', () => {
    renderGrid(true);
    fireEvent.contextMenu(screen.getByTestId('herodraft-attr-grid-str'));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('disables both items for an unavailable hero', () => {
    renderGrid(true);
    fireEvent.contextMenu(hero(PICKED_HERO));
    for (const id of [
      'herodraft-hero-suggest-pick',
      'herodraft-hero-suggest-ban',
    ]) {
      const item = screen.getByTestId(id);
      expect(item).toHaveAttribute('aria-disabled', 'true');
      expect(item).toHaveAttribute('data-disabled');
    }
    fireEvent.click(screen.getByTestId('herodraft-hero-suggest-ban'));
    expect(suggestHero).not.toHaveBeenCalled();
  });

  it('stays enabled when isMyTurn is false', () => {
    renderGrid(true, false);
    fireEvent.contextMenu(hero(FREE_HERO));
    const item = screen.getByTestId('herodraft-hero-suggest-pick');
    expect(item).not.toHaveAttribute('data-disabled');
    fireEvent.click(item);
    expect(suggestHero).toHaveBeenCalledWith('suggest_pick', FREE_HERO);
  });

  it('keeps the hero list mounted when canSuggest flips', () => {
    const grid = (canSuggest: boolean) => (
      <HeroGrid
        onHeroClick={() => {}}
        disabled={false}
        showActionButton
        currentAction="pick"
        isMyTurn
        canSuggest={canSuggest}
      />
    );
    const { rerender } = render(grid(true));
    const list = screen.getByTestId('herodraft-hero-list');
    rerender(grid(false));
    expect(screen.getByTestId('herodraft-hero-list')).toBe(list);
    expect(fireEvent.contextMenu(hero(FREE_HERO))).toBe(true);
    expect(screen.queryByRole('menu')).toBeNull();
    rerender(grid(true));
    expect(screen.getByTestId('herodraft-hero-list')).toBe(list);
  });

  it('closes an open menu when canSuggest turns off and does not reopen it', () => {
    const grid = (canSuggest: boolean) => (
      <HeroGrid
        onHeroClick={() => {}}
        disabled={false}
        showActionButton
        currentAction="pick"
        isMyTurn
        canSuggest={canSuggest}
      />
    );
    const { rerender } = render(grid(true));
    fireEvent.contextMenu(hero(FREE_HERO));
    expect(screen.getByRole('menu')).toBeTruthy();
    rerender(grid(false));
    expect(screen.queryByRole('menu')).toBeNull();
    rerender(grid(true));
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByTestId('herodraft-hero-suggest-menu')).toBeNull();
    fireEvent.contextMenu(hero(PICKED_HERO));
    const menu = screen.getByRole('menu');
    expect(within(menu).getByText(getHeroName(PICKED_HERO))).toBeTruthy();
  });

  it('keeps the native menu on the background when canSuggest is false', () => {
    renderGrid(false);
    expect(
      fireEvent.contextMenu(screen.getByTestId('herodraft-attr-grid-str')),
    ).toBe(true);
  });
});

describe('HeroGrid action tint', () => {
  it.each([
    ['ban', 'bg-ban-surface/80'],
    ['pick', 'bg-pick-surface/80'],
  ] as const)('tints the grid for the team on a %s turn', (action, tint) => {
    render(
      <HeroGrid
        onHeroClick={() => {}}
        disabled
        showActionButton={false}
        currentAction={action}
        isMyTurn
      />,
    );
    expect(screen.getByTestId('herodraft-hero-grid')).toHaveClass(tint);
  });

  it('has no tint when it is not your team’s turn', () => {
    render(
      <HeroGrid
        onHeroClick={() => {}}
        disabled
        showActionButton={false}
        currentAction="ban"
        isMyTurn={false}
      />,
    );
    expect(screen.getByTestId('herodraft-hero-grid')).not.toHaveClass(
      'bg-ban-surface/80',
    );
  });
});

describe('HeroGrid suggestion badges', () => {
  const sender = (pk: number) => ({
    pk,
    username: `u${pk}`,
    nickname: null,
    avatarUrl: null,
    discordId: null,
  });
  let n = 0;
  const suggestion = (
    kind: 'suggest_pick' | 'suggest_ban' | 'unsuggest_pick' | 'unsuggest_ban',
    heroId: number,
    pk: number,
  ) => ({
    id: `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`,
    channel: 'team' as const,
    team_id: 12,
    kind,
    hero_id: heroId,
    body: '',
    created_at: '2026-11-22T00:00:00.000000Z',
    sender: sender(pk),
  });

  function seedSuggestions(messages: ReturnType<typeof suggestion>[]) {
    useHeroDraftStore.setState({ chat: { ...initialChatState, messages } });
  }

  function renderAt(action: 'pick' | 'ban' | undefined, isMyTurn: boolean) {
    render(
      <HeroGrid
        onHeroClick={() => {}}
        disabled={!isMyTurn}
        showActionButton={false}
        currentAction={action}
        isMyTurn={isMyTurn}
        canSuggest
      />,
    );
  }

  const stack = (heroId: number, kind: 'pick' | 'ban') =>
    screen.queryByTestId(`herodraft-hero-${heroId}-${kind}-suggesters`);

  it('shows pick suggesters always and ban suggesters only on a ban stage', () => {
    seedSuggestions([
      suggestion('suggest_pick', FREE_HERO, 1),
      suggestion('suggest_ban', FREE_HERO, 2),
    ]);
    renderAt('pick', false);
    expect(stack(FREE_HERO, 'pick')).toHaveAttribute('data-count', '1');
    expect(stack(FREE_HERO, 'ban')).toBeNull();
  });

  it('shows ban suggesters on a ban stage', () => {
    seedSuggestions([suggestion('suggest_ban', FREE_HERO, 2)]);
    renderAt('ban', false);
    expect(stack(FREE_HERO, 'ban')).toHaveAttribute('data-count', '1');
  });

  it('caps the avatars and shows the overflow count', () => {
    seedSuggestions(
      [1, 2, 3, 4, 5].map((pk) => suggestion('suggest_pick', FREE_HERO, pk)),
    );
    renderAt('pick', false);
    expect(
      screen.getByTestId(`herodraft-hero-${FREE_HERO}-pick-suggesters-more`),
    ).toHaveTextContent('+2');
  });

  it('hides suggestions on a drafted hero and withdrawn ones', () => {
    seedSuggestions([
      suggestion('suggest_pick', PICKED_HERO, 1),
      suggestion('suggest_pick', FREE_HERO, 1),
      suggestion('unsuggest_pick', FREE_HERO, 1),
    ]);
    renderAt('pick', false);
    expect(stack(PICKED_HERO, 'pick')).toBeNull();
    expect(stack(FREE_HERO, 'pick')).toBeNull();
  });

  it('emphasizes suggested picks on your pick turn, not ban-only heroes', () => {
    seedSuggestions([
      suggestion('suggest_pick', FREE_HERO, 1),
      suggestion('suggest_ban', 3, 1),
    ]);
    renderAt('pick', true);
    expect(hero(FREE_HERO)).toHaveAttribute('data-hero-emphasis', 'pick');
    expect(hero(3)).not.toHaveAttribute('data-hero-emphasis');
  });

  it('does not emphasize when it is not your turn', () => {
    seedSuggestions([suggestion('suggest_pick', FREE_HERO, 1)]);
    renderAt('pick', false);
    expect(hero(FREE_HERO)).not.toHaveAttribute('data-hero-emphasis');
  });

  it('offers removal of your own suggestion on right-click', () => {
    const unsuggestHero = vi.fn((): string | null => 'c2');
    useUserStore.setState({ currentUser: { pk: 1 } as never });
    useHeroDraftStore.setState({ unsuggestHero });
    seedSuggestions([
      suggestion('suggest_pick', FREE_HERO, 1),
      suggestion('suggest_ban', FREE_HERO, 2),
    ]);
    renderAt('ban', false);
    fireEvent.contextMenu(hero(FREE_HERO));
    expect(screen.queryByTestId('herodraft-hero-suggest-pick')).toBeNull();
    expect(screen.getByTestId('herodraft-hero-suggest-ban')).toBeTruthy();
    fireEvent.click(screen.getByTestId('herodraft-hero-unsuggest-pick'));
    expect(unsuggestHero).toHaveBeenCalledWith('suggest_pick', FREE_HERO);
    useUserStore.setState(originalUser, true);
  });
});
