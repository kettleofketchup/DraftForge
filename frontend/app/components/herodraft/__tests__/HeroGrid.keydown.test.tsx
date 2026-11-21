// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

import { HeroGrid } from '~/components/herodraft/HeroGrid';
import type { HeroDraft } from '~/components/herodraft/types';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from '~/components/ui/sheet';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const original = useHeroDraftStore.getState();

beforeEach(() => {
  useHeroDraftStore.setState({
    draft: { rounds: [] } as unknown as HeroDraft,
    searchQuery: '',
    selectedHeroId: null,
  });
});
afterEach(() => useHeroDraftStore.setState(original, true));

const grid = (
  <HeroGrid onHeroClick={() => {}} disabled showActionButton={false} />
);
const search = () => screen.getByTestId('herodraft-hero-search');

describe('HeroGrid global keydown', () => {
  it('focuses hero search for a printable key on the page', () => {
    render(grid);
    fireEvent.keyDown(document.body, { key: 'a' });
    expect(document.activeElement).toBe(search());
  });

  it('leaves Enter to the chat keybind', () => {
    render(grid);
    fireEvent.keyDown(document.body, { key: 'Enter' });
    expect(document.activeElement).not.toBe(search());
  });

  it('still focuses search when the grid itself sits inside an open dialog', () => {
    render(
      <div role="dialog" data-state="open">
        {grid}
      </div>,
    );
    fireEvent.keyDown(document.body, { key: 'a' });
    expect(document.activeElement).toBe(search());
  });

  it('ignores keys targeted inside the chat', () => {
    render(
      <>
        {grid}
        <div data-herodraft-chat="">
          <button type="button" data-testid="chat-toggle">
            chat
          </button>
        </div>
      </>,
    );
    const toggle = screen.getByTestId('chat-toggle');
    toggle.focus();
    fireEvent.keyDown(toggle, { key: 'a' });
    expect(document.activeElement).toBe(toggle);
    fireEvent.keyDown(toggle, { key: 'Escape' });
    expect(document.activeElement).toBe(toggle);
  });

  it('ignores keys while a sheet is open over the grid', () => {
    render(
      <>
        {grid}
        <Sheet open>
          <SheetContent side="bottom">
            <SheetTitle>Sheet</SheetTitle>
            <SheetDescription>over the grid</SheetDescription>
            <button type="button" data-testid="sheet-button">
              x
            </button>
          </SheetContent>
        </Sheet>
      </>,
    );
    const focusSpy = vi.spyOn(search(), 'focus');
    const button = screen.getByTestId('sheet-button');
    button.focus();
    fireEvent.keyDown(button, { key: 'a' });
    fireEvent.keyDown(document.body, { key: 'a' });
    expect(focusSpy).not.toHaveBeenCalled();
  });

  it('ignores keys targeted inside an open menu', () => {
    render(
      <>
        {grid}
        <div role="menu">
          <div role="menuitem" tabIndex={-1} data-testid="item">
            item
          </div>
        </div>
      </>,
    );
    const item = screen.getByTestId('item');
    item.focus();
    fireEvent.keyDown(item, { key: 's' });
    expect(document.activeElement).toBe(item);
  });
});
