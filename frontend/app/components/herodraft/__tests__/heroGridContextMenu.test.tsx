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

const PICKED_HERO = 1;
const FREE_HERO = 2;

const suggestHero = vi.fn(
  (_kind: string, _heroId: number): string | null => 'c1',
);
const original = useHeroDraftStore.getState();

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
