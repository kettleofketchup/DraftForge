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

import { HeroGrid } from '~/components/herodraft/HeroGrid';
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

  it('suggests a ban and opens the chat panel', () => {
    renderGrid(true);
    fireEvent.contextMenu(hero(FREE_HERO));
    fireEvent.click(screen.getByTestId('herodraft-hero-suggest-ban'));
    expect(suggestHero).toHaveBeenCalledWith('suggest_ban', FREE_HERO);
    expect(useHeroDraftStore.getState().chat.panelOpen).toBe(true);
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
});
