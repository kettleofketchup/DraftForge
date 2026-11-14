// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LocationProbe } from '~/test-utils/LocationProbe';
import '../changelog/ChangelogPreview';
import { MobileNav } from '../MobileNav';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/data/CHANGELOG.md?raw', async () => ({
  default: (await import('~/lib/__tests__/changelog-fixture'))
    .CHANGELOG_FIXTURE,
}));
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: { currentUser: object }) => unknown) =>
    selector({ currentUser: {} }),
}));

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

function openDrawer(): void {
  render(
    <MemoryRouter>
      <MobileNav />
      <LocationProbe />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByTestId('mobileNavToggle'));
}

afterEach(() => {
  cleanup();
});

describe('MobileNav Docs section', () => {
  it('shows the latest releases inline only after expanding', async () => {
    openDrawer();
    expect(screen.queryByTestId('mobile-nav-changelog-preview')).toBeNull();

    const trigger = screen.getByTestId('mobile-nav-docs-trigger');
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    expect(
      await screen.findByRole('heading', { level: 3, name: /2\.1\.0/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 3, name: /2\.0\.0/ }),
    ).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /1\.0\.0/ })).toBeNull();
    expect(
      screen.getByRole('heading', { level: 2, name: 'nav.whats_new' }),
    ).toBeTruthy();

    const preview = screen.getByTestId('mobile-nav-changelog-preview');
    expect(preview.querySelector('[data-slot="scroll-area"]')).toBeNull();

    const docsLink = screen.getByRole('link', { name: 'nav.docs' });
    expect(docsLink.getAttribute('target')).toBe('_blank');
    expect(docsLink.getAttribute('rel')).toBe('noopener noreferrer');

    expect(screen.getByTestId('mobile-nav-report-issue-link')).toBeTruthy();
  });

  it('closes the drawer when following the full changelog link', async () => {
    openDrawer();
    fireEvent.click(screen.getByTestId('mobile-nav-docs-trigger'));
    await screen.findByRole('heading', { level: 3, name: /2\.1\.0/ });

    const fullLink = screen.getByTestId('mobile-nav-changelog-full-link');
    expect(fullLink.getAttribute('href')).toBe('/changelog');
    fireEvent.click(fullLink);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/changelog');
  });
});
