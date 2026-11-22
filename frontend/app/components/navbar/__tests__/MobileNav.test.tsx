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
const userState = vi.hoisted(() => ({
  currentUser: {} as { username?: string },
}));
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: typeof userState) => unknown) =>
    selector(userState),
}));
vi.mock('~/components/user/UserAvatar', () => ({
  UserAvatar: () => <span data-testid="drawer-avatar" />,
}));
vi.mock('~/components/user/avatar', () => ({
  DisplayName: (user: { username?: string }) => user.username ?? '',
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

function openDrawer(path = '/'): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <MobileNav />
      <LocationProbe />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByTestId('mobileNavToggle'));
}

afterEach(() => {
  cleanup();
  userState.currentUser = {};
});

describe('MobileNav account row', () => {
  it('tells a logged-out visitor so and links to Discord login', () => {
    openDrawer('/leagues/3?tab=info');
    const row = screen.getByTestId('mobile-nav-login');
    expect(row.textContent).toContain('login');
    expect(row.textContent).toContain('account.logged_out');
    expect(row.getAttribute('href')).toBe(
      `/login/discord/?next=${encodeURIComponent('/leagues/3?tab=info')}`,
    );
    expect(screen.queryByTestId('mobile-nav-account')).toBeNull();
  });

  it('shows the logged-in user with a profile link', () => {
    userState.currentUser = { username: 'kettle' };
    openDrawer();
    const row = screen.getByTestId('mobile-nav-account');
    expect(row.getAttribute('href')).toBe('/profile');
    expect(row.textContent).toContain('kettle');
    expect(row.textContent).toContain('account.logged_in');
    expect(screen.getByTestId('drawer-avatar')).toBeTruthy();
    expect(screen.queryByTestId('mobile-nav-login')).toBeNull();
  });
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
    expect(fullLink.textContent).toBe('nav.full_changelog');
    fireEvent.click(fullLink);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/changelog');
  });

  it('styles the Docs row like its sibling drawer rows', () => {
    openDrawer();
    const trigger = screen.getByTestId('mobile-nav-docs-trigger');
    expect(trigger.getAttribute('type')).toBe('button');
    expect(trigger.className).toContain('hover:bg-muted');
    expect(trigger.className).not.toMatch(/scale|accent/);
  });
});
