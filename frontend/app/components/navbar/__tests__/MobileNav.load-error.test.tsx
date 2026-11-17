// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LocationProbe } from '~/test-utils/LocationProbe';
import { MobileNav } from '../MobileNav';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: { currentUser: object }) => unknown) =>
    selector({ currentUser: {} }),
}));
vi.mock('../changelog/ChangelogPreview', () => {
  throw new Error('chunk gone');
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

describe('MobileNav Docs section when the preview chunk fails', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('closes the drawer from the fallback full changelog link', async () => {
    render(
      <MemoryRouter>
        <MobileNav />
        <LocationProbe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('mobileNavToggle'));
    fireEvent.click(screen.getByTestId('mobile-nav-docs-trigger'));

    expect(await screen.findByText('nav.changelog_load_error')).toBeTruthy();
    const fallbackLink = within(
      screen.getByTestId('mobile-nav-changelog-preview'),
    ).getByRole('link', { name: 'nav.full_changelog' });
    expect(fallbackLink.getAttribute('href')).toBe('/changelog');
    fireEvent.click(fallbackLink);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/changelog');
  });
});
