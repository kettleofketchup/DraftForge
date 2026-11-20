// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { Trophy } from 'lucide-react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FeatureCard } from '../FeatureCard';

// Make the lazy thumbnail load at once: visible immediately, idle callback runs now.
beforeEach(() => {
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(private cb: IntersectionObserverCallback) {}
      observe() {
        this.cb(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('requestIdleCallback', (cb: () => void) => {
    cb();
    return 1;
  });
});

afterEach(() => vi.unstubAllGlobals());

function renderCard() {
  render(
    <MemoryRouter>
      <FeatureCard
        icon={Trophy}
        title="Brackets"
        description="Bracket preview"
        gifSrc="https://assets.example/bracket.png"
      />
    </MemoryRouter>,
  );
  return screen.getByAltText('Brackets preview');
}

const spinner = () => document.querySelector('.animate-spin');

describe('FeatureCard thumbnail', () => {
  it('drops the spinner once the thumbnail loads', () => {
    const img = renderCard();
    expect(spinner()).not.toBeNull();
    fireEvent.load(img);
    expect(spinner()).toBeNull();
  });

  it('shows a fallback instead of spinning forever when the thumbnail fails', () => {
    const img = renderCard();
    fireEvent.error(img);
    expect(spinner()).toBeNull();
    expect(screen.getByTestId('lazy-image-error')).toHaveTextContent(
      'Preview unavailable',
    );
    expect(screen.queryByAltText('Brackets preview')).toBeNull();
  });
});
