// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

import { HeroGrid } from '~/components/herodraft/HeroGrid';
import type { HeroDraft } from '~/components/herodraft/types';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const original = useHeroDraftStore.getState();

beforeEach(() => {
  useHeroDraftStore.setState({
    draft: { rounds: [] } as unknown as HeroDraft,
    searchQuery: '',
    selectedHeroId: null,
    chatPanelInset: 0,
  });
});
afterEach(() => useHeroDraftStore.setState(original, true));

const list = () => screen.getByTestId('herodraft-hero-list');

describe('HeroGrid chat panel inset', () => {
  it('pads and scrolls the hero list only while the chat panel covers it', () => {
    render(
      <HeroGrid onHeroClick={() => {}} disabled showActionButton={false} />,
    );
    expect(list().style.paddingBottom).toBe('');
    expect(list()).not.toHaveClass('overflow-y-auto');

    act(() => useHeroDraftStore.setState({ chatPanelInset: 312 }));
    expect(list().style.paddingBottom).toBe('312px');
    expect(list().style.scrollPaddingBottom).toBe('312px');
    expect(list()).toHaveClass('overflow-y-auto');
    expect(screen.getByTestId('herodraft-attr-section-all')).toHaveClass(
      'min-h-fit',
    );

    act(() => useHeroDraftStore.setState({ chatPanelInset: 0 }));
    expect(list().style.paddingBottom).toBe('');
    expect(screen.getByTestId('herodraft-attr-section-all')).toHaveClass(
      'min-h-0',
    );
  });
});
